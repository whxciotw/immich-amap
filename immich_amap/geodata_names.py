"""地名数据源（可选输入）：全量中文别名 + 高德反查缓存。

这两个数据源都只在**构建 geodata 时**读取，产物仍是普通 GeoNames 文本；
Immich 运行时（导入 ``/build/geodata``）不依赖任何网络或这些源文件。

- :func:`build_alternate_index`：读 GeoNames ``alternateNamesV2.txt``，
  按 geonameid 取中文别名（过滤历史名/俗称/非纯中文，繁体转简体）。
- :func:`load_amap_cache` / :func:`pick_admin_name`：读高德反查缓存 CSV，
  按目标粒度（city/county/town）挑一级行政区名。

设计约束：

1. 只索引 ``cities500.txt`` 里出现过的 geonameid（``wanted_ids``），
   避免把几百 MB 的别名表全塞进内存；
2. 同名不同地只按 **geonameid** 关联，绝不按名字关联；
3. 高德返回的行政级别名可能带 ``省/市/区/镇`` 后缀或空数组，这里统一清洗，
   供 :mod:`immich_amap.geodata` 直接写进 ``name`` 列。
"""

from __future__ import annotations

import csv
import pathlib

from .geodata_tables import CJK, T2S

#: alternateNamesV2 里算「中文」的 isolanguage 取值（按优先级从高到低）
ZH_LANGS: tuple[str, ...] = (
    "zh",
    "zh-Hans",
    "zh-CN",
    "zh-SG",
    "zh-Hant",
    "zh-HK",
    "zh-TW",
    "zh-MO",
)

_ZH_RANK = {lang: rank for rank, lang in enumerate(ZH_LANGS)}

#: 高德缓存 CSV 的行政区列（对应 addressComponent 的 province/city/district/township）
AMAP_ADMIN_KEYS: tuple[str, ...] = ("admin1", "admin2", "admin3", "admin4")

#: 目标粒度 → 依次尝试的行政区列（由细到粗兜底）
LEVEL_ADMIN_ORDER: dict[str, tuple[str, ...]] = {
    # city 档最后兜底 admin3：省直辖县级市（仙桃/济源等）没有 admin2，
    # 高德只给「省直辖县级行政区划」占位值和省名，真正的市名在 district 里
    "city": ("admin2", "admin1", "admin3"),
    "county": ("admin3", "admin2", "admin1"),
    "town": ("admin4", "admin3", "admin2", "admin1"),
}

#: 高德对港澳台/直辖市会返回「XX特别行政区」这类全称，写成显示名前先收敛
_ADMIN_SUFFIXES: tuple[str, ...] = ("特别行政区",)

_COUNTRY_WORDS = ("中华人民共和国", "中国", "中國")

#: 高德会把「省直辖县级行政区划」这类占位值当作行政区名返回，必须当空处理
_PLACEHOLDERS = frozenset({"省直辖县级行政区划", "自治区直辖县级行政区划", "市辖区", "市辖县"})


_CONVERTER: list = []
_CONVERTER_READY = False


def _converter() -> object | None:
    """返回一个 ``str -> str`` 的繁转简函数；没有可用后端时返回 None。

    优先用 ``zhconv``，其次 ``opencc``（两者都是**可选**依赖，只影响构建期转换质量，
    不影响运行期）；都没有就退回 :data:`immich_amap.geodata_tables.T2S`
    （由 OpenCC 对本地名库实际用字生成的 251 字表，覆盖面有限）。
    """
    global _CONVERTER_READY
    if not _CONVERTER_READY:
        _CONVERTER_READY = True
        try:
            from zhconv import convert as zhconv_convert

            _CONVERTER.append(lambda text: zhconv_convert(text, "zh-cn"))
        except ImportError:
            try:
                from opencc import OpenCC

                opencc = OpenCC("t2s")
                _CONVERTER.append(opencc.convert)
            except ImportError:
                _CONVERTER.append(None)
    return _CONVERTER[0]


def to_simplified(name: str) -> str:
    """繁转简（**默认路径只用内置 251 字表**，保证默认档不受可选依赖影响）。"""
    return "".join(T2S.get(char, char) for char in name)


def to_simplified_alias(name: str) -> str:
    """别名索引专用繁转简：装了 zhconv/opencc 时全量转换，否则退回内置字表。"""
    convert = _converter()
    if convert is not None:
        return convert(name)
    return to_simplified(name)


def build_alternate_index(
    path: pathlib.Path,
    wanted_ids: set[str] | None = None,
) -> dict[str, str]:
    """从 ``alternateNamesV2.txt`` 建 ``geonameid → 中文名`` 索引。

    ``alternateNamesV2.txt`` 每行 10 列（tab 分隔）::

        alternateNameId  geonameid  isolanguage  alternate name  isPreferredName
        isShortName  isColloquial  isHistoric  from  to

    取值规则：语言优先级见 :data:`ZH_LANGS`，同语言 ``isPreferredName=1`` 优先，
    再取更短的名字；丢掉历史名、俗称、非纯中文名和「中国」这类国家名。
    """
    if wanted_ids is None:
        wanted: set[str] | None = None
    else:
        wanted = wanted_ids

    best: dict[str, tuple[tuple[int, int, int], str]] = {}
    with open(path, encoding="utf-8-sig") as handle:
        for line in handle:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 8:
                continue
            gid = parts[1]
            if wanted is not None and gid not in wanted:
                continue
            rank = _ZH_RANK.get(parts[2])
            if rank is None:
                continue
            name = parts[3].strip()
            if not name or not CJK.fullmatch(name):
                continue
            if name.startswith(_COUNTRY_WORDS):
                continue
            if parts[5] == "1":  # isShortName（「沪」这类缩写不要写进 city）
                continue
            if parts[6] == "1" or parts[7] == "1":  # isColloquial / isHistoric
                continue
            order = (rank, 0 if parts[4] == "1" else 1, len(name))
            current = best.get(gid)
            if current is None or order < current[0]:
                best[gid] = (order, to_simplified_alias(name))

    return {gid: name for gid, (_order, name) in best.items()}


def load_amap_cache(path: pathlib.Path) -> dict[str, dict[str, str]]:
    """读高德反查缓存 CSV（``geonameid,admin1,admin2,admin3,admin4``）。

    多出来的列（``cc/lat/lon/fetched_at`` 等）忽略；空行与缺 id 的行跳过。
    """
    cache: dict[str, dict[str, str]] = {}
    if path.stat().st_size == 0:
        return cache
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "geonameid" not in reader.fieldnames:
            raise ValueError(f"{path} 不是高德缓存 CSV（缺 geonameid 表头）")
        for row in reader:
            gid = (row.get("geonameid") or "").strip()
            if not gid:
                continue
            cache[gid] = {key: (row.get(key) or "").strip() for key in AMAP_ADMIN_KEYS}
    return cache


def _clean_admin_name(name: str) -> str:
    """清洗高德行政区名：去空白、占位值、国家全称、「特别行政区」后缀。"""
    name = name.strip().replace(" ", "").replace("\u3000", "")
    if not name or name in _COUNTRY_WORDS or name in _PLACEHOLDERS:
        return ""
    for suffix in _ADMIN_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
    return name


def looks_like_city_admin(name: str) -> bool:
    """admin1 只能当「城市」用的情况：直辖市（以市结尾）或港澳台。

    高德对「省直辖县级行政区划」的点会只返回 ``province="浙江省"`` 且 ``city=[]``；
    直接采用会写出「浙江 · 浙江省」这种脏值，所以省份级 admin1 一律不采用。
    """
    return name.endswith("市") or name in ("香港", "澳门", "台湾")


def has_usable_admin(record: dict[str, str]) -> bool:
    """缓存行是否值得保留：有区县/乡镇级，或 admin1 是直辖市/港澳台。

    「只有省份名」的结果对地名库没用（省直辖县级市、农村点常见），别写进缓存。
    """
    if any(_clean_admin_name(record.get(key, "")) for key in ("admin2", "admin3", "admin4")):
        return True
    return looks_like_city_admin(_clean_admin_name(record.get("admin1", "")))


def _city_admin_order(record: dict[str, str]) -> tuple[str, ...] | None:
    """city 档的 admin 优先级；返回 None 表示「不覆盖，保留启发式名字」。

    - 港澳：city 档保留原有「香港/路氹城」这类显示，避免退化成只有「澳门」；
    - 自治州/地区/盟：admin2 是「黔西南布依族苗族自治州」这种长名，优先用 admin3（兴义市）；
    - 其余：admin2（苏州市）> admin1（上海市）> admin3。
    """
    admin1 = _clean_admin_name(record.get("admin1", ""))
    admin2 = _clean_admin_name(record.get("admin2", ""))
    if admin1 in ("香港", "澳门"):
        return None
    if admin2 and admin2.endswith(("州", "地区", "盟")) and not admin2.endswith("市"):
        return ("admin3", "admin2", "admin1")
    return LEVEL_ADMIN_ORDER["city"]


def pick_admin_name_with_key(record: dict[str, str], level: str) -> tuple[str, str]:
    """按目标粒度挑行政区名，返回 ``(名字, 命中的列名)``；没有合适的返回空串。

    ``geodata`` 用命中的列名来判定这一行算哪一级的锚点（admin2=城市、admin3=区县、
    admin4=乡镇），从而支撑 ``--level county/town``。
    """
    order = _city_admin_order(record) if level == "city" else LEVEL_ADMIN_ORDER.get(level, LEVEL_ADMIN_ORDER["city"])
    if order is None:
        return "", ""
    for key in order:
        name = _clean_admin_name(record.get(key, ""))
        if not name or not CJK.fullmatch(name) or name.startswith(_COUNTRY_WORDS):
            continue
        if key == "admin1" and not looks_like_city_admin(name):
            continue
        return name, key
    return "", ""


def pick_admin_name(record: dict[str, str], level: str) -> str:
    """按目标粒度从高德缓存里挑一个行政区名；没有合适的返回空串。"""
    return pick_admin_name_with_key(record, level)[0]
