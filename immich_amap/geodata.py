"""把 Immich 的本地地名库改造成「中文优先 + 可控粒度」。

Immich v3 用镜像内 ``/build/geodata`` 的 GeoNames 数据做逆地理编码：

- 城市名取 ``cities500.txt`` 第 2 列 ``name``（英文/罗马化），第 4 列
  ``alternateNames`` 里的中文不参与显示；
- 取「25km 内最近的地名」，SQL 只按距离排序，**不分行政级别** —— 所以会出现
  「村/镇/乡」；
- 配置里 ``reverseGeocoding`` 只有 ``enabled`` 一个开关，**没有语言选项**。

本模块做四件事：

1. **中文化**：``name`` 列按优先级取名字 —— 人工覆盖（``NAME_OVERRIDE``）>
   高德缓存（``--amap-cache``）> 全量中文别名（``--alternate-names``）>
   ``cities500`` 第 4 列的中文别名 > 原名；``admin1CodesASCII.txt`` 的中国省级、
   ``countryInfo.txt`` 的国家名也换成中文。
2. **增强点集**（``--enhance``）：把 GeoNames 国家全量 dump 里人口达标的点并进
   ``cities500``，补上 25km 内原本没有地名的空白；``--full`` 不做人口过滤。
3. **粒度归一化**（``--level city|county|town``）：把「非目标级别」的行改写成
   最近的目标级别地名（优先同省，其次同国，150km 内）；``town`` 保留有中文名的行，
   没中文名的行按 city 档归一到最近城市（避免英文村镇名进 ``city`` 字段）。
4. **显示名**（``--prefix province|none`` + ``--separator``）：默认把「省 · 市」
   直接写进 ``name`` 列（Web/手机地点页都只渲染 ``city`` 字段）。

最后写新的 ``geodata-date.txt``，触发 Immich 重新导入。

城市判定规则见 ``docs/geodata-cn.md``；规则表在 :mod:`immich_amap.geodata_tables`；
数据源解析在 :mod:`immich_amap.geodata_names` 与 :mod:`immich_amap.geodata_amap`。

用法::

    python3 -m immich_amap geodata --src /tmp/geo --dst /tmp/geo-out
    python3 -m immich_amap geodata --src /tmp/geo --dst /tmp/geo-out \\
        --enhance ~/geo-cache/CN.txt --alternate-names ~/geo-cache/alternateNamesV2.txt
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import shutil
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone

from .geodata_names import (
    build_alternate_index,
    load_amap_cache,
    pick_admin_name_with_key,
    to_simplified,
)
from .geodata_tables import (
    CJK,
    CN_ADMIN1,
    CN_CITY_CODES,
    COUNTRY_OVERRIDE,
    NAME_OVERRIDE,
    POP_CITY_THRESHOLD,
    PPLC_LIKE,
    RENAME_RADIUS_KM,
    SPECIAL_ADMIN1,
    SUB_UNIT,
    SUFFIX_SCORE,
)

#: 需要读取 / 输出的 geodata 文件（顺序与日志一致）
GEODATA_FILES: tuple[str, ...] = (
    "cities500.txt",
    "admin1CodesASCII.txt",
    "admin2Codes.txt",
    "countryInfo.txt",
    "ne_10m_admin_0_countries.geojson",
)

#: 粒度档位：city=地级市，county=区县，town=乡镇/村（不归一化）
LEVELS: tuple[str, ...] = ("city", "county", "town")

#: 显示前缀：province=「省 · 市」，none=只写地名
PREFIXES: tuple[str, ...] = ("province", "none")

#: 默认显示分隔符
DEFAULT_SEPARATOR = " · "

#: 区县级锚点的名字后缀
COUNTY_SUFFIXES: tuple[str, ...] = ("区", "县", "旗")

#: 村镇级后缀（这些不算区县级锚点）
TOWN_SUFFIXES: tuple[str, ...] = ("镇", "乡", "村", "街道", "屯")


# --------------------------------------------------------------------------
# 纯函数：中文名挑选 / 繁简转换 / 城市判定 / 显示名
# --------------------------------------------------------------------------
def pick_cjk(alternates: Iterable[str]) -> str | None:
    """从 GeoNames 的 alternateNames 里挑一个最像「地名」的纯中文别名。

    优先级：``市`` > ``城/区/县/镇/乡/村/岛/港/湾`` > 其它；同分取更短、再按码点。
    """
    candidates = [alt for alt in alternates if CJK.match(alt) and not alt.startswith("中国")]
    if not candidates:
        return None

    def rank(name: str) -> tuple[int, int, str]:
        score = 2
        for suffix, value in SUFFIX_SCORE:
            if name.endswith(suffix):
                score = value
                break
        return (score, len(name), name)

    return min(candidates, key=rank)


def is_city(item: Mapping) -> bool:
    """判断一条地名记录是否算「城市」（city 级别的锚点）。

    - 名字必须是纯中文、且不是「区/县/镇/乡/村/街道」这类下级单位；
    - 中国： GeoNames feature code 为 PPLC/PPLA/PPLA2，或「以市结尾且人口 ≥ 30 万」
      （GeoNames 对个别地级市标成了 PPL，如临汾）；
    - 其他国家/地区：PPLC/PPLA/PPLA2 或人口 ≥ 10 万。
    """
    name, country, code, population = item["name"], item["cc"], item["code"], item["pop"]
    if not CJK.match(name):
        return False
    if name.endswith(SUB_UNIT):
        return False
    if country == "CN":
        return code in CN_CITY_CODES or (name.endswith("市") and population >= 300_000)
    return code in PPLC_LIKE or population >= POP_CITY_THRESHOLD


def is_county_anchor(item: Mapping) -> bool:
    """判断一条记录是否算「区县级锚点」（用于 ``--level county``）。

    - 高德缓存命中 admin3（区/县）的直接算；
    - 否则要求纯中文、不是「镇/乡/村/街道/屯」后缀，且 ``PPLA3`` 或以「区/县/旗」结尾
      （个别 ``PPLA3`` 点名字是「XX镇」，按村镇处理，避免区县档反而显示镇名）。
    """
    name = str(item.get("name", ""))
    if not CJK.fullmatch(name):
        return False
    if name.endswith(TOWN_SUFFIXES):
        return False
    if item.get("amap_kind") == "admin3":
        return True
    return bool(item.get("code") == "PPLA3" or name.endswith(COUNTY_SUFFIXES))


def _is_anchor(item: Mapping, level: str) -> bool:
    """某一粒度下的锚点判定（锚点不会被归一化改写）。"""
    if "lat" not in item:
        return False
    if level == "town":
        # town 档：每个「有中文名」的点都是锚点；没中文名的点按 city 档归一到最近城市，
        # 避免把英文村镇名直接写进 city 字段
        return bool(CJK.fullmatch(str(item.get("name", ""))))
    if is_city(item) or item.get("amap_kind") in ("admin1", "admin2"):
        return True
    if level == "county":
        return is_county_anchor(item)
    return False


class Grid:
    """0.5° 网格索引，用于快速找「离我最近的锚点」。"""

    def __init__(self, cell: float = 0.5) -> None:
        self.cell = cell
        self.buckets: dict[tuple[int, int], list[dict]] = defaultdict(list)

    def key(self, lat: float, lon: float) -> tuple[int, int]:
        return (int(math.floor(lat / self.cell)), int(math.floor(lon / self.cell)))

    def add(self, item: Mapping) -> None:
        # 直接存引用：锚点建好索引后不会再被改名（改名的是非锚点行），
        # 省掉 dict 拷贝在 100 万行 `--enhance --full` 时约 1GB 内存。
        self.buckets[self.key(item["lat"], item["lon"])].append(item)

    def _ring_cells(self, cell_lat: int, cell_lon: int, ring: int):
        """按 Chebyshev 距离由近到远枚举网格单元（ring=0 是查询点所在格）。"""
        if ring == 0:
            yield (cell_lat, cell_lon)
            return
        for dlat in range(-ring, ring + 1):
            yield (cell_lat + dlat, cell_lon - ring)
            yield (cell_lat + dlat, cell_lon + ring)
        for dlon in range(-ring + 1, ring):
            yield (cell_lat - ring, cell_lon + dlon)
            yield (cell_lat + ring, cell_lon + dlon)

    def nearest(
        self,
        lat: float,
        lon: float,
        max_km: float,
        accept: Callable[[dict], bool] = lambda _item: True,
    ) -> dict | None:
        """返回 ``max_km`` 内按 ``accept`` 过滤后最近的一条记录。

        按环由近到远搜索，并在「后续环不可能更近」时提前退出 —— 基线库上与原实现
        结果一致，但在 `--level county --enhance --full` 这种 100 万行的场景下快一个量级。
        """
        cell_lat, cell_lon = self.key(lat, lon)
        # 高纬度处 1 经度对应的公里数会收缩，span 与环终止下界都必须按 cos 修正，
        # 否则北欧/加拿大等地的锚点会被漏掉（实测纬度 68°+ 会漏）
        cos_lat = max(math.cos(math.radians(min(85.0, abs(lat) + 3 * self.cell))), 0.05)
        cell_km = self.cell * 111.32 * cos_lat
        max_span = int(max_km / cell_km) + 1
        best: tuple[float, dict] | None = None
        for ring in range(max_span + 1):
            for cell in self._ring_cells(cell_lat, cell_lon, ring):
                for item in self.buckets.get(cell, ()):
                    if not accept(item):
                        continue
                    delta_lat = (item["lat"] - lat) * 111.32
                    delta_lon = (item["lon"] - lon) * 111.32 * math.cos(math.radians(lat))
                    distance = math.hypot(delta_lat, delta_lon)
                    if distance <= max_km and (best is None or distance < best[0]):
                        best = (distance, item)
            # 第 ring+1 环及更外层的点，距离至少是 ring*cell_km
            if best is not None and best[0] <= ring * cell_km:
                break
        return best[1] if best else None

    def __len__(self) -> int:
        return sum(len(bucket) for bucket in self.buckets.values())


# --------------------------------------------------------------------------
# 数据加载
# --------------------------------------------------------------------------
def load_country_zh(geojson_path: pathlib.Path) -> dict[str, str]:
    """从 Natural Earth 的 ``NAME_ZH`` 取国家中文名，再套一层习惯写法覆盖。"""
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    names: dict[str, str] = {}
    for feature in data.get("features", []):
        properties = feature.get("properties") or {}
        for key in ("ISO_A2", "ISO_A2_EH"):
            iso = properties.get(key)
            name_zh = properties.get("NAME_ZH")
            if iso and iso != "-99" and name_zh:
                names.setdefault(iso, name_zh.strip())
    names.update(COUNTRY_OVERRIDE)
    return names


def load_country_english(country_info: pathlib.Path) -> dict[str, str]:
    """读原始 ``countryInfo.txt`` 的英文国家名（第 5 列）。"""
    names: dict[str, str] = {}
    for line in country_info.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) > 4:
            names[fields[0]] = fields[4].strip()
    return names


def load_admin1_names(admin1_path: pathlib.Path) -> dict[str, str]:
    """``admin1CodesASCII.txt`` → ``{"CN.31": "上海"}``。"""
    names: dict[str, str] = {}
    for line in admin1_path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) > 1 and fields[0]:
            names[fields[0]] = fields[1]
    return names


def display_name(
    cc: str,
    admin1: str,
    city: str,
    *,
    country_zh: Mapping[str, str],
    country_en: Mapping[str, str],
    admin1_map: Mapping[str, str],
    prefix: str = "province",
    separator: str = DEFAULT_SEPARATOR,
) -> str:
    """拼显示名。

    - ``prefix="province"``（默认）：中国 / 港澳台前缀取省级中文名（港澳台统一成
      「香港/澳门/台湾」）；境外优先中文国家名（境外 admin1 没有中文译名，避免中英混排）；
    - ``prefix="none"``：只写地名本身；
    - 直辖市等「省=市」的情况收敛成一段，避免「上海 · 上海市」。
    """
    if not city:
        return city
    if prefix == "none":
        return city
    if cc in SPECIAL_ADMIN1:
        province = SPECIAL_ADMIN1[cc]
    else:
        province = admin1_map.get(f"{cc}.{admin1}")

    if cc == "CN" or cc in SPECIAL_ADMIN1:
        head = province
    else:
        head = country_zh.get(cc) or country_en.get(cc) or province

    if not head:
        return city
    if city == head or city == f"{head}市":
        return city
    return f"{head}{separator}{city}"


# --------------------------------------------------------------------------
# 名字解析（多个数据源按优先级）
# --------------------------------------------------------------------------
def _parse_population(raw: str) -> int:
    try:
        return int(raw or 0)
    except ValueError:
        return 0


def _normalize_admin_name(name: str) -> str:
    """清洗高德行政区名（去「特别行政区」后缀、滤掉国家全称）。"""
    name = name.strip()
    if name.endswith("特别行政区") and len(name) > 5:
        name = name[:-5]
    if name in ("中华人民共和国", "中国"):
        return ""
    return name


def resolve_name(
    parts: list[str],
    *,
    alternates: Mapping[str, str] | None = None,
    amap: Mapping[str, Mapping[str, str]] | None = None,
    level: str = "city",
) -> tuple[str, str, str]:
    """按优先级解析一行的显示名，返回 ``(name, source, amap_kind)``。

    优先级：``NAME_OVERRIDE`` > 高德缓存 > cities500 第 4 列 > 原名。

    注意：``alternates`` 参数只在直接调用 :func:`load_cities` 时生效；``run()`` 走的是
    :func:`apply_alternates`，只给「还没有中文名」的行补全量别名（不覆盖已有中文名）。
    """
    if len(parts) < 2:
        return "", "original", ""
    gid = parts[0]
    override = NAME_OVERRIDE.get(gid)
    if override:
        return override, "override", ""

    if amap:
        record = amap.get(gid)
        if record:
            name, kind = pick_admin_name_with_key(record, level)
            name = _normalize_admin_name(name)
            if name:
                return name, "amap", kind

    if alternates:
        alt = alternates.get(gid)
        if alt:
            return to_simplified(alt), "alternate", ""

    if len(parts) > 3:
        cjk = pick_cjk(parts[3].split(","))
        if cjk:
            return to_simplified(cjk), "cities500", ""

    return to_simplified(parts[1]), "original", ""


def _make_item(
    parts: list[str],
    *,
    alternates: Mapping[str, str] | None = None,
    amap: Mapping[str, Mapping[str, str]] | None = None,
    level: str = "city",
    origin: str = "cities500",
) -> dict:
    """把一行 19 列的 GeoNames 记录变成内部 item（名字已解析）。"""
    name, source, kind = resolve_name(parts, alternates=alternates, amap=amap, level=level)
    item: dict = {
        "parts": parts,
        "name": name,
        "source": source,
        "origin": origin,
        "original_name": parts[1],
    }
    if kind:
        item["amap_kind"] = kind
    if len(parts) >= 15:
        try:
            latitude = float(parts[4])
            longitude = float(parts[5])
        except ValueError:
            return {"parts": parts}  # 坏坐标行原样保留，不让整库构建失败
        item.update(
            lat=latitude,
            lon=longitude,
            cc=parts[8],
            a1=parts[10],
            code=parts[7],
            pop=_parse_population(parts[14]),
        )
    return item


def load_cities(
    path: pathlib.Path,
    *,
    alternates: Mapping[str, str] | None = None,
    amap: Mapping[str, Mapping[str, str]] | None = None,
    level: str = "city",
) -> tuple[list[dict], int, int]:
    """读 ``cities500.txt``，名字先按数据源解析好。

    返回 ``(items, 总行数, 改名行数)``；字段不足 15 列的行原样保留。
    """
    items: list[dict] = []
    total = renamed = 0
    with open(path, encoding="utf-8-sig") as handle:
        for line in handle:
            parts = line.rstrip("\r\n").split("\t")
            total += 1
            if len(parts) < 15:
                items.append({"parts": parts})
                continue
            item = _make_item(parts, alternates=alternates, amap=amap, level=level)
            if "lat" not in item:
                items.append(item)
                continue
            if item["name"] != item["original_name"]:
                renamed += 1
            parts[1] = item["name"]
            items.append(item)
    return items, total, renamed


def merge_enhance_rows(
    items: list[dict],
    paths: Iterable[pathlib.Path],
    *,
    min_pop: int = 100,
    full: bool = False,
    alternates: Mapping[str, str] | None = None,
    amap: Mapping[str, Mapping[str, str]] | None = None,
    level: str = "city",
) -> int:
    """把 GeoNames 国家 dump 里符合条件的点并进 ``items``，返回新增行数。

    过滤：feature class 必须是 ``P``（populated place）；默认人口 ≥ ``min_pop``，
    ``full=True`` 时不做人口过滤；按 geonameid 与 (lat, lon) 双去重。
    """
    existing_ids = {item["parts"][0] for item in items if item.get("parts")}
    existing_coords = {(item["parts"][4], item["parts"][5]) for item in items if "lat" in item}
    seen_ids: set[str] = set()
    seen_coords: set[tuple[str, str]] = set()
    added = 0

    for path in paths:
        with open(path, encoding="utf-8-sig") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 15 or parts[6] != "P":
                    continue
                gid = parts[0]
                if gid in existing_ids or gid in seen_ids:
                    continue
                if not full and _parse_population(parts[14]) < min_pop:
                    continue
                coord = (parts[4], parts[5])
                if coord in existing_coords or coord in seen_coords:
                    continue
                item = _make_item(parts, alternates=alternates, amap=amap, level=level, origin="enhance")
                if "lat" not in item:
                    continue
                parts[1] = item["name"]
                items.append(item)
                seen_ids.add(gid)
                seen_coords.add(coord)
                added += 1
    return added


def apply_alternates(items: list[dict], alternates: Mapping[str, str]) -> int:
    """给「还没有中文名」的行补全量别名（P0-2），返回改写行数。"""
    applied = 0
    for item in items:
        if "lat" not in item or item.get("source") in ("amap", "override"):
            continue
        if CJK.fullmatch(str(item.get("name", ""))):
            continue
        alt = alternates.get(item["parts"][0])
        if not alt:
            continue
        item["name"] = alt
        item["source"] = "alternate"
        item["parts"][1] = alt
        applied += 1
    return applied


# --------------------------------------------------------------------------
# 改写步骤
# --------------------------------------------------------------------------
def rewrite_country_info(src: pathlib.Path, dst: pathlib.Path, country_zh: Mapping[str, str]) -> int:
    """``countryInfo.txt``：国家名换成中文。返回改动行数。"""
    lines, changed = [], 0
    for line in (src / "countryInfo.txt").read_text(encoding="utf-8").splitlines(keepends=True):
        if line.startswith("#") or not line.strip():
            lines.append(line)
            continue
        fields = line.rstrip("\r\n").split("\t")
        name_zh = country_zh.get(fields[0])
        if name_zh and len(fields) > 4:
            fields[4] = name_zh
            changed += 1
        lines.append("\t".join(fields) + "\n")
    (dst / "countryInfo.txt").write_text("".join(lines), encoding="utf-8")
    return changed


def rewrite_admin1(src: pathlib.Path, dst: pathlib.Path) -> int:
    """``admin1CodesASCII.txt``：中国省级、港澳台换成中文。返回改动行数。"""
    lines, changed = [], 0
    for line in (src / "admin1CodesASCII.txt").read_text(encoding="utf-8").splitlines(keepends=True):
        fields = line.rstrip("\r\n").split("\t")
        cc = fields[0].split(".", 1)[0] if "." in fields[0] else ""
        name_zh = None
        if cc == "CN":
            name_zh = CN_ADMIN1.get(fields[1])
        elif cc in SPECIAL_ADMIN1:
            name_zh = SPECIAL_ADMIN1[cc]
        if name_zh and len(fields) > 2:
            fields[1] = name_zh
            fields[2] = name_zh
            changed += 1
        lines.append("\t".join(fields) + "\n")
    (dst / "admin1CodesASCII.txt").write_text("".join(lines), encoding="utf-8")
    return changed


def apply_display_names(
    items: list[dict],
    *,
    level: str,
    prefix: str,
    separator: str,
    country_zh: Mapping[str, str],
    country_en: Mapping[str, str],
    admin1_map: Mapping[str, str],
) -> int:
    """给锚点行写「省 · 市」显示名（只改中文名行，避免英文名被加前缀）。"""
    decorated = 0
    for item in items:
        if "lat" not in item or not _is_anchor(item, level):
            continue
        if not CJK.fullmatch(str(item.get("name", ""))):
            continue
        item["display"] = to_simplified(
            display_name(
                item["cc"],
                item["a1"],
                item["name"],
                country_zh=country_zh,
                country_en=country_en,
                admin1_map=admin1_map,
                prefix=prefix,
                separator=separator,
            )
        )
        item["parts"][1] = item["display"]
        decorated += 1
    return decorated


def _nearest_in(grid: Grid | None, lat: float, lon: float) -> dict | None:
    """在某个索引里找 150km 内最近锚点；索引不存在时返回 None。"""
    if grid is None:
        return None
    return grid.nearest(lat, lon, RENAME_RADIUS_KM)


def normalize_to_anchors(
    items: list[dict],
    level: str,
    *,
    display_for: Callable[[dict], str] | None = None,
) -> tuple[int, int]:
    """非锚点行改写成最近锚点的名字。返回 ``(锚点数, 改写行数)``。

    ``display_for`` 用于「任意中文名兜底」时给非锚点中文行拼显示名（见下）。
    """
    anchors = [item for item in items if _is_anchor(item, level)]

    # town 档只把「没有中文名」的行改写成最近城市名；网格只用城市锚点，
    # 否则 100 万级的村镇锚点会让最近邻查询退化到分钟级。
    if level == "town":
        # 有中文名的行保持原样；没中文名的行按 city 档兜底到最近城市。
        # 用「全部中文锚点」会更贴近村镇语义，但 112 万行时最近邻会慢到分钟级（实测 >60s），
        # 这里选择性能与「不把英文名写进 city」的折中。
        grid_anchors = [item for item in items if _is_anchor(item, "city")] or anchors
    else:
        grid_anchors = anchors

    # 三层索引：同省 → 同国 → 全局。搜索只扫小网格，避免 100 万行 × 全国锚点。
    by_admin1: dict[tuple[str, str], Grid] = defaultdict(Grid)
    by_country: dict[str, Grid] = defaultdict(Grid)
    global_grid = Grid()
    for item in grid_anchors:
        global_grid.add(item)
        by_admin1[(item["cc"], item["a1"])].add(item)
        by_country[item["cc"]].add(item)

    rewritten = 0
    for item in items:
        if "lat" not in item or _is_anchor(item, level):
            continue
        # 优先同省（保证「省 · 市」前缀与 state 一致），其次同国，最后任意
        anchor = _nearest_in(by_admin1.get((item["cc"], item["a1"])), item["lat"], item["lon"])
        if anchor is None:
            anchor = _nearest_in(by_country.get(item["cc"]), item["lat"], item["lon"])
        if anchor is not None and anchor["a1"] != item["a1"]:
            item["parts"][10] = anchor["a1"]  # 跨省兜底时对齐省级
            item["a1"] = anchor["a1"]
        if anchor is None:
            anchor = _nearest_in(global_grid, item["lat"], item["lon"])
        if anchor is not None:
            item["name"] = anchor["name"]
            item["display"] = anchor.get("display", anchor["name"])
            item["parts"][1] = item["display"]
            rewritten += 1

    # 兜底：150km 内没有目标级锚点时，用「任意有中文名的行」兜底一次。
    # 否则旧版能（虽然是错的地名）显示中文的点会退化成英文（如瑙鲁/阿根廷小地方）。
    unhandled = [
        item
        for item in items
        if "lat" in item
        and not _is_anchor(item, level)
        and "display" not in item
        and not CJK.fullmatch(str(item.get("name", "")))
    ]
    if unhandled:
        cjk_rows = [item for item in items if "lat" in item and CJK.fullmatch(str(item.get("name", "")))]
        if cjk_rows:
            cjk_global = Grid()
            cjk_by_admin1: dict[tuple[str, str], Grid] = defaultdict(Grid)
            cjk_by_country: dict[str, Grid] = defaultdict(Grid)
            for item in cjk_rows:
                cjk_global.add(item)
                cjk_by_admin1[(item["cc"], item["a1"])].add(item)
                cjk_by_country[item["cc"]].add(item)
            for item in unhandled:
                anchor = _nearest_in(cjk_by_admin1.get((item["cc"], item["a1"])), item["lat"], item["lon"])
                if anchor is None:
                    anchor = _nearest_in(cjk_by_country.get(item["cc"]), item["lat"], item["lon"])
                if anchor is None:
                    anchor = _nearest_in(cjk_global, item["lat"], item["lon"])
                if anchor is None:
                    continue
                item["name"] = anchor["name"]
                if display_for is not None:
                    item["display"] = display_for(anchor)
                else:
                    item["display"] = anchor.get("display", anchor["name"])
                item["parts"][1] = item["display"]
                rewritten += 1
    return len(anchors), rewritten


def normalize_to_city_level(items: list[dict]) -> tuple[int, int]:
    """兼容旧接口：按城市级归一化。"""
    return normalize_to_anchors(items, "city")


def write_cities(path: pathlib.Path, items: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for item in items:
            handle.write("\t".join(item["parts"]) + "\n")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def run(
    src: pathlib.Path,
    dst: pathlib.Path,
    *,
    city_level: bool = True,
    level: str = "city",
    prefix: str = "province",
    separator: str = DEFAULT_SEPARATOR,
    enhance: Iterable[pathlib.Path] | None = None,
    enhance_min_pop: int = 100,
    full: bool = False,
    alternate_names: pathlib.Path | None = None,
    amap_cache: pathlib.Path | None = None,
    quiet: bool = False,
) -> dict:
    """执行完整改写，返回统计信息（供测试/调用方使用）。

    ``city_level=False`` 是旧参数：只中文化、不做任何归一化（等价于历史行为）。
    """
    if level not in LEVELS:
        raise ValueError(f"未知粒度: {level}（可选 {', '.join(LEVELS)}）")
    if prefix not in PREFIXES:
        raise ValueError(f"未知前缀模式: {prefix}（可选 {', '.join(PREFIXES)}）")
    if not separator or any(char in separator for char in "\t\r\n"):
        raise ValueError("separator 不能为空，也不能包含制表符/换行（会破坏 TSV 列结构）")

    src = pathlib.Path(src)
    dst = pathlib.Path(dst)
    if src.resolve() == dst.resolve():
        raise ValueError("--dst 不能与 --src 相同（会覆盖原始 geodata）")
    enhance_paths = [pathlib.Path(path) for path in enhance or []]
    amap = load_amap_cache(amap_cache) if amap_cache else None

    def out(message: str) -> None:
        if not quiet:
            print(message)

    dst.mkdir(parents=True, exist_ok=True)
    country_zh = load_country_zh(src / "ne_10m_admin_0_countries.geojson")
    country_en = load_country_english(src / "countryInfo.txt")

    changed_country = rewrite_country_info(src, dst, country_zh)
    changed_admin1 = rewrite_admin1(src, dst)

    admin1_map = load_admin1_names(dst / "admin1CodesASCII.txt")
    items, total, renamed = load_cities(src / "cities500.txt", amap=amap, level=level)

    enhanced = 0
    if enhance_paths:
        enhanced = merge_enhance_rows(
            items,
            enhance_paths,
            min_pop=enhance_min_pop,
            full=full,
            amap=amap,
            level=level,
        )
        threshold = "不设人口阈值" if full else f"min_pop={enhance_min_pop}"
        out(f"增强点集：并入 {enhanced} 行（{len(enhance_paths)} 个 dump 文件，{threshold}）")

    amap_rows = sum(1 for item in items if item.get("source") == "amap")
    if amap:
        out(f"高德缓存：载入 {len(amap)} 条，命中 {amap_rows} 行")

    alternates: dict[str, str] = {}
    alternates_applied = 0
    if alternate_names:
        wanted = {item["parts"][0] for item in items if "lat" in item}
        alternates = build_alternate_index(alternate_names, wanted)
        alternates_applied = apply_alternates(items, alternates)
        out(f"全量别名：索引 {len(alternates)} 条，补中文名 {alternates_applied} 行")

    decorated = apply_display_names(
        items,
        level=level,
        prefix=prefix,
        separator=separator,
        country_zh=country_zh,
        country_en=country_en,
        admin1_map=admin1_map,
    )
    city_named_rows = sum(1 for item in items if "lat" in item and is_city(item))
    city_rows = city_named_rows if city_level else 0

    def display_for(item: dict) -> str:
        return to_simplified(
            display_name(
                item["cc"],
                item["a1"],
                item["name"],
                country_zh=country_zh,
                country_en=country_en,
                admin1_map=admin1_map,
                prefix=prefix,
                separator=separator,
            )
        )

    anchor_rows = decorated
    rewritten = 0
    if city_level:
        anchor_rows, rewritten = normalize_to_anchors(items, level, display_for=display_for)
        out(f"粒度归一化：level={level}，锚点 {anchor_rows}，改写 {rewritten} 行")
    else:
        out("跳过归一化（--no-city-level）")

    write_cities(dst / "cities500.txt", items)
    for name in ("admin2Codes.txt", "ne_10m_admin_0_countries.geojson"):
        shutil.copyfile(src / name, dst / name)

    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (dst / "geodata-date.txt").write_text(stamp, encoding="utf-8")

    separated = sum(1 for item in items if separator and separator in str(item.get("display", "")))
    stats = {
        "country_renamed": changed_country,
        "admin1_renamed": changed_admin1,
        "cities_total": total,
        "rows_total": total + enhanced,
        "cities_renamed": renamed + sum(
            1
            for item in items
            if item.get("origin") == "cities500" and item.get("source") == "alternate"
        ),
        "city_rows": city_rows,
        "city_named_rows": city_named_rows,
        "anchor_rows": anchor_rows,
        "rewritten_rows": rewritten,
        "display_with_separator": separated,
        "enhance_rows": enhanced,
        "alternate_rows": alternates_applied,
        "amap_rows": amap_rows,
        "level": level,
        "prefix": prefix,
        "separator": separator,
        "stamp": stamp,
    }
    out(f"countryInfo : {changed_country} 个国家名改中文")
    out(f"admin1      : {changed_admin1} 个省级名改中文")
    suffix = f"（另并增强 {enhanced} 行）" if enhanced else ""
    out(f"cities500   : {stats['cities_renamed']}/{total} 行取了中文名{suffix}")
    out(f"显示名形如「省{separator}市」的行: {separated}")
    out(f"输出目录: {dst}")
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="immich_amap geodata",
        description="把 Immich 的 GeoNames 地名库改造成「中文 + 可控粒度」",
    )
    parser.add_argument("--src", type=pathlib.Path, required=True, help="原始 geodata 目录（容器 /build/geodata 拷出）")
    parser.add_argument("--dst", type=pathlib.Path, required=True, help="输出目录")
    parser.add_argument(
        "--level",
        choices=list(LEVELS),
        default="city",
        help="粒度：city=地级市（默认）/ county=区县 / town=乡镇（有中文名就不归一化）",
    )
    parser.add_argument(
        "--prefix",
        choices=list(PREFIXES),
        default="province",
        help="显示前缀：province=「省 · 市」（默认）/ none=只写地名",
    )
    parser.add_argument("--separator", default=DEFAULT_SEPARATOR, help="前缀与地名的分隔符（默认「 · 」）")
    parser.add_argument(
        "--no-city-level",
        action="store_true",
        help="旧参数：只中文化，不做任何归一化（保持历史行为）",
    )
    parser.add_argument(
        "--enhance",
        type=pathlib.Path,
        action="append",
        metavar="DUMP",
        help="并入 GeoNames 国家全量 dump（可重复；如 CN.txt/HK.txt）",
    )
    parser.add_argument("--enhance-min-pop", type=int, default=100, help="增强点集的人口阈值（默认 100）")
    parser.add_argument("--full", action="store_true", help="增强点集不做人口过滤（对应上游 _full）")
    parser.add_argument(
        "--alternate-names",
        type=pathlib.Path,
        metavar="FILE",
        help="GeoNames alternateNamesV2.txt（补全量中文别名）",
    )
    parser.add_argument(
        "--amap-cache",
        type=pathlib.Path,
        metavar="CSV",
        help="高德反查缓存 CSV（由 amap-cache 子命令生成）",
    )
    args = parser.parse_args(argv)

    missing = [name for name in GEODATA_FILES if not (args.src / name).exists()]
    if missing:
        parser.error(f"{args.src} 缺少文件: {', '.join(missing)}")
    for path in [args.alternate_names, args.amap_cache, *(args.enhance or [])]:
        if path is not None and not path.is_file():
            parser.error(f"文件不存在: {path}")

    try:
        run(
            args.src,
            args.dst,
            city_level=not args.no_city_level,
            level=args.level,
            prefix=args.prefix,
            separator=args.separator,
            enhance=args.enhance,
            enhance_min_pop=args.enhance_min_pop,
            full=args.full,
            alternate_names=args.alternate_names,
            amap_cache=args.amap_cache,
        )
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
