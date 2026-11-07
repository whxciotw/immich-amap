"""端到端自测：解开 ``data:`` URL，代入真实瓦片坐标逐条抓取，验证「贴进去能出图」。

改造前的根目录 ``selftest.py``。

默认从 ``dist/urls.txt`` 读取样式，取北京天安门附近的真实瓦片坐标（WGS-84），
把 ``{x}/{y}/{z}`` 替换后逐个 source 抓取，检查是否返回 200 与 256x256 图片。

有 Pillow 时校验图片尺寸/模式；没有 Pillow 时退化为校验 ``Content-Type``，
不会因为缺依赖误报失败。
"""

from __future__ import annotations

import argparse
import io
import math
import pathlib
import sys
import urllib.error
import urllib.request

from .urls import decode_data_url

#: 默认取样点：北京天安门（WGS-84）与缩放级别
DEFAULT_LON, DEFAULT_LAT, DEFAULT_ZOOM = 116.3912, 39.9062, 16

try:  # Pillow 是可选依赖，只用于校验图片尺寸
    from PIL import Image

    HAVE_PIL = True
except ImportError:  # pragma: no cover - 取决于运行环境
    HAVE_PIL = False


def tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """WGS-84 经纬度 → Web Mercator 瓦片编号。"""
    n = 2**zoom
    x = (lon + 180) / 360 * n
    lat_rad = math.radians(lat)
    y = (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n
    return int(x), int(y)


def load_styles(path: pathlib.Path) -> dict[str, dict]:
    """解析 ``urls.txt``（``## 名称`` 后跟一行 ``data:`` URL）。"""
    styles: dict[str, dict] = {}
    name = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            name = line[3:].split("(")[0].strip()
        elif line.startswith("data:") and name:
            styles[name] = decode_data_url(line)
    return styles


def check_style(
    name: str,
    style: dict,
    *,
    limit: int = 1,
    timeout: float = 30.0,
    lon: float = DEFAULT_LON,
    lat: float = DEFAULT_LAT,
    zoom: int = DEFAULT_ZOOM,
) -> bool:
    """抓取一个样式里各 source 的瓦片，返回是否全部通过。"""
    x, y = tile_xy(lon, lat, zoom)
    ok = True
    for source_id, source in style.get("sources", {}).items():
        for template in source.get("tiles", [])[:limit]:
            url = template.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(zoom))
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = response.read()
                    content_type = response.headers.get("Content-Type", "")
                ok &= _check_tile(name, source_id, data, content_type)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                ok = False
                print(f"  [{name}/{source_id}] FAIL {exc!r}  {url[:110]}")
    return ok


def _check_tile(name: str, source_id: str, data: bytes, content_type: str) -> bool:
    if HAVE_PIL:
        try:
            image = Image.open(io.BytesIO(data))
        except Exception:  # noqa: BLE001 - 非图片的响应都算失败
            print(f"  [{name}/{source_id}] {len(data):6d}B  非图片! ({content_type})")
            return False
        dims = f"{image.size[0]}x{image.size[1]} {image.mode}"
        passed = image.size == (256, 256)
        print(f"  [{name}/{source_id}] {len(data):6d}B  {dims}")
        return passed
    passed = content_type.startswith("image/") and len(data) > 0
    print(f"  [{name}/{source_id}] {len(data):6d}B  {content_type}（未装 Pillow，跳过尺寸校验）")
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="immich_amap selftest",
        description="端到端抓图自测：验证样式里的瓦片地址能否出图",
    )
    parser.add_argument(
        "--urls",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[1] / "dist" / "urls.txt",
        help="data: URL 清单（默认 <仓库>/dist/urls.txt）",
    )
    parser.add_argument("--url", default=None, help="只测单条 data: URL")
    parser.add_argument("--limit", type=int, default=1, help="每个 source 测前 N 条瓦片模板")
    parser.add_argument("--timeout", type=float, default=30.0, help="单条请求超时（秒）")
    parser.add_argument(
        "--at",
        default=f"{DEFAULT_LON},{DEFAULT_LAT},{DEFAULT_ZOOM}",
        help="取样点「经度,纬度,缩放」，默认天安门附近 z16",
    )
    args = parser.parse_args(argv)

    if args.url:
        styles = {"(cli)": decode_data_url(args.url)}
    else:
        if not args.urls.exists():
            parser.error(f"找不到 {args.urls}，请先运行 python3 -m immich_amap urls")
        styles = load_styles(args.urls)

    try:
        lon, lat, zoom = (float(v) for v in args.at.split(","))
    except ValueError:
        parser.error(f"--at 应为「经度,纬度,缩放」: {args.at!r}")

    all_ok = True
    for name, style in styles.items():
        print(f"\n{name}: {len(style.get('sources', {}))} 个 source")
        all_ok &= check_style(
            name,
            style,
            limit=args.limit,
            timeout=args.timeout,
            lon=lon,
            lat=lat,
            zoom=int(zoom),
        )

    print("\n全部通过 ✅" if all_ok else "\n有失败 ❌（自建服务可加 --url 单测）")
    return 0 if all_ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
