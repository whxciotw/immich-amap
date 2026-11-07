"""高德反向地理编码缓存（P1-1「精修」的可选数据源）。

**主流程不联网**：本模块只在你想精修地名时单独运行一次，把结果落成 CSV
（``geonameid,admin1,admin2,admin3,admin4``），之后 ``geodata`` 子命令用
``--amap-cache`` 读取。网络失败/配额用尽只会让这次精修失败，已生成的地名库不受影响。

要点：

1. **只查需要的点**：用 ``--coords`` 传你的资产坐标，按 Immich 的「25km 内最近点」
   规则反推出真正会被用到的 geodata 行，避免对全量几十万点做无谓调用；
2. **坐标转换**：高德只接受 GCJ-02，这里自带 WGS-84 → GCJ-02 转换（不引入依赖）；
3. **限流与增量**：``--qps`` 控制请求速率，``--batch-size`` 单次最多 20 个坐标，
   输出文件是增量的，重复运行会跳过已缓存的 geonameid。

**已知假设**：批量响应按请求顺序返回（高德文档如此，但未逐次实测）。若担心顺序错乱，
可先用 ``--batch-size 1`` 跑小样本抽查；缓存是按 geonameid 增量复用的，错了需删 CSV 重跑。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import pathlib
import sys
import time
import urllib.request
from datetime import datetime, timezone

from .geodata_names import AMAP_ADMIN_KEYS, has_usable_admin, load_amap_cache

AMAP_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"

#: 高德覆盖范围（中国大陆/港澳），范围外不做转换与反查
CHINA_BOUNDS = (72.004, 0.8293, 137.8347, 55.8271)  # lon_min, lat_min, lon_max, lat_max

#: 与 Immich 一致的搜索半径（km）
IMMICH_RADIUS_KM = 25.0

_A = 6378245.0
_EE = 0.00669342162296594323
_PI = math.pi


# --------------------------------------------------------------------------
# WGS-84 → GCJ-02
# --------------------------------------------------------------------------
def _out_of_china(lat: float, lon: float) -> bool:
    lon_min, lat_min, lon_max, lat_max = CHINA_BOUNDS
    return not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * _PI) + 40.0 * math.sin(y / 3.0 * _PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * _PI) + 320 * math.sin(y * _PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * _PI) + 40.0 * math.sin(x / 3.0 * _PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * _PI) + 300.0 * math.sin(x / 30.0 * _PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
    """WGS-84 坐标转 GCJ-02（高德坐标系）；中国范围外原样返回。"""
    if _out_of_china(lat, lon):
        return lat, lon
    delta_lat = _transform_lat(lon - 105.0, lat - 35.0)
    delta_lon = _transform_lon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * _PI
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    delta_lat = (delta_lat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * _PI)
    delta_lon = (delta_lon * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * _PI)
    return lat + delta_lat, lon + delta_lon


# --------------------------------------------------------------------------
# 响应解析 / 请求
# --------------------------------------------------------------------------
def _as_text(value: object) -> str:
    """高德空字段会返回 ``[]``，统一成空串。"""
    if isinstance(value, list):
        return ""
    return str(value or "").strip()


def parse_regeo(payload: dict) -> list[dict[str, str]]:
    """解析高德 regeo 响应，返回与请求坐标同序的行政区列表。

    ``batch=true`` 时结果在 ``regeocodes``；单点时在 ``regeocode``。
    """
    records = payload.get("regeocodes")
    if not isinstance(records, list):
        single = payload.get("regeocode")
        records = [single] if isinstance(single, dict) and single else []
    parsed: list[dict[str, str]] = []
    for record in records:
        component = {}
        if isinstance(record, dict):
            component = record.get("addressComponent") or {}
        parsed.append(
            {
                "admin1": _as_text(component.get("province")),
                "admin2": _as_text(component.get("city")),
                "admin3": _as_text(component.get("district")),
                "admin4": _as_text(component.get("township")),
            }
        )
    return parsed


def build_regeo_params(api_key: str, coordinates: list[tuple[float, float]], radius_m: int = 1000) -> dict[str, str]:
    """拼一批坐标的查询参数（坐标是 GCJ-02 的 ``lon,lat``）。"""
    location = "|".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coordinates)
    return {
        "location": location,
        "key": api_key,
        "batch": "true",
        "radius": str(radius_m),
        "extensions": "base",
        "output": "json",
    }


def _default_http_get(url: str, params: dict[str, str], timeout: float) -> dict:
    query = "&".join(f"{key}={urllib.request.quote(str(value), safe=',|.')}" for key, value in params.items())
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "immich-amap/geodata"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - 固定 https 域名
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 不要带出 URL/query（里面有 key）
        raise RuntimeError(f"高德请求失败：HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"高德请求失败：{exc.reason}") from None


class _RateLimiter:
    """按 QPS 控制请求节奏（不依赖第三方库）。"""

    def __init__(self, qps: float) -> None:
        self.interval = 1.0 / qps if qps > 0 else 0.0
        self._next = 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        now = time.monotonic()
        if self._next > now:
            time.sleep(self._next - now)
        self._next = max(now, self._next) + self.interval


def _write_rows(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    new_file = not path.exists() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["geonameid", "cc", "lat", "lon", *AMAP_ADMIN_KEYS, "fetched_at"])
        for row in rows:
            writer.writerow(
                [
                    row["geonameid"],
                    row.get("cc", ""),
                    f"{row.get('lat', '')}",
                    f"{row.get('lon', '')}",
                    *(row.get(key, "") for key in AMAP_ADMIN_KEYS),
                    row.get("fetched_at", ""),
                ]
            )
    # 缓存里含资产附近的坐标与行政区名，按 0600 收紧（多用户 NAS 上别被其他账号读）
    try:
        path.chmod(0o600)
    except OSError:
        pass


def fetch_cache(
    candidates: list[dict[str, str]],
    api_key: str,
    out_path: pathlib.Path,
    *,
    qps: float = 3.0,
    batch_size: int = 20,
    timeout: float = 10.0,
    limit: int | None = None,
    quiet: bool = False,
    http_get=None,
) -> int:
    """批量反查并**增量**写入缓存 CSV，返回本次新写入的行数。

    ``http_get`` 可注入（测试用），签名 ``(url, params, timeout) -> dict``。
    """
    http_get = http_get or _default_http_get
    if not 1 <= batch_size <= 20:
        raise ValueError("batch_size 必须在 1~20 之间")
    existing = load_amap_cache(out_path) if out_path.exists() else {}
    pending = [item for item in candidates if item["geonameid"] not in existing]
    if limit is not None:
        pending = pending[:limit]

    limiter = _RateLimiter(qps)
    written = 0
    for offset in range(0, len(pending), batch_size):
        chunk = pending[offset : offset + batch_size]
        coordinates = [wgs84_to_gcj02(float(item["lat"]), float(item["lon"])) for item in chunk]
        limiter.wait()
        payload = http_get(AMAP_REGEO_URL, build_regeo_params(api_key, coordinates), timeout)
        if str(payload.get("status")) != "1":
            raise RuntimeError(f"高德返回错误: {payload.get('info') or payload}")
        parsed = parse_regeo(payload)
        if len(parsed) != len(chunk):
            raise RuntimeError(f"高德返回条数不匹配: 请求 {len(chunk)} 条，返回 {len(parsed)} 条")

        stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows = [
            {
                "geonameid": item["geonameid"],
                "cc": item.get("cc", ""),
                "lat": item.get("lat", ""),
                "lon": item.get("lon", ""),
                **result,
                "fetched_at": stamp,
            }
            for item, result in zip(chunk, parsed)
            # 只有省份名（省直辖县级市/农村点常见）对地名库没用（会被当脏值丢弃），
            # 全部为空同理 —— 都不落缓存，下次还能重试
            if has_usable_admin(result)
        ]
        if rows:
            _write_rows(out_path, rows)
        written += len(rows)
        if not quiet:
            print(f"高德反查：{written}/{len(pending)} 条已写入 {out_path}")
    return written


# --------------------------------------------------------------------------
# 候选点收集
# --------------------------------------------------------------------------
def read_coords(path: pathlib.Path) -> list[tuple[float, float]]:
    """读资产坐标 CSV。

    支持两种格式：
    - 带表头：按 ``latitude/lat``、``longitude/lon/lng`` 列名取；
    - 无表头：前两列按 ``lat,lon`` 解释。
    """
    coords: list[tuple[float, float]] = []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        return coords

    header = [cell.strip().lower() for cell in rows[0]]
    lat_index = next((index for index, name in enumerate(header) if name in ("latitude", "lat")), None)
    lon_index = next((index for index, name in enumerate(header) if name in ("longitude", "lon", "lng")), None)
    start = 0
    if lat_index is None or lon_index is None:
        lat_index, lon_index, start = 0, 1, 0

    for row in rows[start:]:
        try:
            latitude = float(row[lat_index])
            longitude = float(row[lon_index])
        except (ValueError, IndexError):
            continue
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            continue  # nan/inf 会让网格索引直接崩，按坏行跳过
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        coords.append((latitude, longitude))
    return coords


def collect_candidates(
    src: pathlib.Path,
    coords: list[tuple[float, float]],
    *,
    radius_km: float = IMMICH_RADIUS_KM,
) -> list[dict[str, str]]:
    """按 Immich「25km 内最近点」规则，把资产坐标映射到 geodata 行。"""
    from .geodata import Grid, load_cities  # 延迟导入，避免循环依赖

    items, _total, _renamed = load_cities(src / "cities500.txt")
    grid = Grid()
    for item in items:
        if "lat" in item and item["cc"] in ("CN", "HK", "MO"):
            grid.add(item)

    found: dict[str, dict[str, str]] = {}
    for lat, lon in coords:
        hit = grid.nearest(lat, lon, radius_km)
        if hit is None:
            continue
        gid = hit["parts"][0]
        found.setdefault(
            gid,
            {
                "geonameid": gid,
                "cc": hit["cc"],
                "lat": str(hit["lat"]),
                "lon": str(hit["lon"]),
                "name": hit["name"],
            },
        )
    return list(found.values())


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="immich-amap amap-cache",
        description="用高德反向地理编码生成 geodata 精修缓存（可选，不联网不影响主流程）",
    )
    parser.add_argument("--src", type=pathlib.Path, required=True, help="原始 geodata 目录（容器 /build/geodata 拷出）")
    parser.add_argument("--out", type=pathlib.Path, required=True, help="输出缓存 CSV（增量）")
    parser.add_argument("--coords", type=pathlib.Path, help="资产坐标 CSV（lat,lon 或带 latitude/longitude 表头）")
    parser.add_argument("--all", action="store_true", help="反查 src 里所有 CN/HK/MO 点（配额消耗大，建议配 --limit）")
    parser.add_argument("--limit", type=int, help="本次最多反查多少行")
    parser.add_argument("--qps", type=float, default=3.0, help="每秒请求数（默认 3）")
    parser.add_argument("--batch-size", type=int, default=20, help="单次批量坐标数（高德上限 20）")
    parser.add_argument("--timeout", type=float, default=10.0, help="单次请求超时秒数")
    parser.add_argument(
        "--include-named",
        action="store_true",
        help="仅 --all 模式有效：连已有中文名的点也精修（--coords 模式默认全查）",
    )
    parser.add_argument("--key-env", default="AMAP_API_KEY", help="读取高德 key 的环境变量名")
    args = parser.parse_args(argv)

    if not args.coords and not args.all:
        parser.error("要么用 --coords 指定资产坐标（推荐），要么用 --all 全量反查")
    if args.coords and not args.coords.is_file():
        parser.error(f"--coords 文件不存在: {args.coords}")
    if not 1 <= args.batch_size <= 20:
        parser.error("--batch-size 必须在 1~20 之间")
    if args.qps <= 0:
        parser.error("--qps 必须大于 0")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit 必须大于 0")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")

    api_key = os.environ.get(args.key_env, "").strip()
    if not api_key:
        parser.error(f"未找到高德 key：请设置环境变量 {args.key_env}")

    src: pathlib.Path = args.src
    if not (src / "cities500.txt").is_file():
        parser.error(f"{src} 下没有 cities500.txt")

    if args.all:
        from .geodata import load_cities  # 延迟导入

        items, _total, _renamed = load_cities(src / "cities500.txt")
        candidates = [
            {
                "geonameid": item["parts"][0],
                "cc": item["cc"],
                "lat": str(item["lat"]),
                "lon": str(item["lon"]),
                "name": item["name"],
            }
            for item in items
            if "lat" in item and item["cc"] in ("CN", "HK", "MO")
        ]
    else:
        coordinates = read_coords(args.coords)
        if not coordinates:
            parser.error(f"{args.coords} 里没有读到坐标")
        candidates = collect_candidates(src, coordinates)

    # --coords 已按资产坐标收窄了范围，默认全查（区县/乡镇级别需要这些点的 admin3/4）；
    # --all 会命中几十万行，默认只补还没中文名的点，避免烧配额。
    if args.all and not args.include_named:
        candidates = [item for item in candidates if not _has_chinese(item.get("name", ""))]

    if not candidates:
        print("没有需要反查的点（都已有中文名或附近没有 geodata 行）")
        return 0

    print(f"待反查 {len(candidates)} 个 geodata 行 → {args.out}")
    written = fetch_cache(
        candidates,
        api_key,
        args.out,
        qps=args.qps,
        batch_size=args.batch_size,
        timeout=args.timeout,
        limit=args.limit,
    )
    print(f"完成：本次写入 {written} 行，缓存文件 {args.out}")
    return 0


def _has_chinese(name: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in name)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
