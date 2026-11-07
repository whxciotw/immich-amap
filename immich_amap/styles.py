"""MapLibre style 构建。

三个变体：

- ``light``  —— 高德路网 + 注记（亮色）
- ``dark``   —— 同一套路网瓦片，用 ``raster-*`` 滤镜压暗（高德没有暗色栅格瓦片）
- ``sat``    —— 卫星影像 + 路网注记两个图层叠加（天然偏暗，亮/暗模式都能用）

每个变体都有「纠偏」与「不纠偏」两版，由 :class:`immich_amap.tiles.TileSet`
决定瓦片地址；是否纠偏不影响 style 结构，只影响 ``sources.*.tiles``。

滤镜只作用于底图图层，不会影响 Immich 叠加在上面的照片标记。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .tiles import ATTRIBUTION, MAX_ZOOM, MIN_ZOOM, TileSet

VARIANTS: tuple[str, ...] = ("light", "dark", "sat")

#: 各变体的画布底色（瓦片未加载/越界时可见）
BACKGROUND_COLORS: Mapping[str, str] = {
    "light": "#f2f3f5",
    "dark": "#0e1116",
    "sat": "#0e1116",
}

#: 暗色路网：高德没有暗色瓦片，用亮度/饱和度/对比度压暗
DARK_ROAD_PAINT: Mapping[str, float] = {
    "raster-brightness-max": 0.52,
    "raster-saturation": -0.65,
    "raster-contrast": 0.05,
}

#: 暗色卫星注记可再压一层亮度（当前未启用，保留给自定义样式）
DARK_SATELLITE_PAINT: Mapping[str, float] = {"raster-brightness-max": 0.72}


def coord_note(fixed: bool) -> str:
    """样式名里标注坐标系处理方式。"""
    return "GCJ-02→WGS-84 纠偏" if fixed else "WGS-84 未纠偏"


def json_dumps(style: Mapping) -> str:
    """写盘用的可读 JSON（URL 编码另用 :func:`immich_amap.urls.dumps`）。"""
    return json.dumps(style, ensure_ascii=False, indent=2)


def style_name(variant: str, tile_set: TileSet) -> str:
    """生成输出文件名，如 ``amap-light`` / ``amap-fixed-sat``。"""
    if variant not in VARIANTS:
        raise ValueError(f"未知样式变体: {variant!r}（可选 {', '.join(VARIANTS)}）")
    prefix = "amap-fixed-" if tile_set.fixed else "amap-"
    return f"{prefix}{variant}"


def display_name(variant: str, tile_set: TileSet) -> str:
    """写进 style ``name`` 字段的名字。"""
    titles = {"light": "AMap Road Light", "dark": "AMap Road Dark", "sat": "AMap Satellite+Labels"}
    return f"{titles[variant]} ({coord_note(tile_set.fixed)})"


def raster_source(
    tile_urls: Sequence[str],
    *,
    attribution: str | None = ATTRIBUTION,
) -> dict:
    """构造一个 raster source 定义。"""
    source: dict = {
        "type": "raster",
        "tiles": list(tile_urls),
        "tileSize": 256,
        "minzoom": MIN_ZOOM,
        "maxzoom": MAX_ZOOM,
    }
    if attribution:
        source["attribution"] = attribution
    return source


def _background_layer(variant: str) -> dict:
    return {
        "id": "bg",
        "type": "background",
        "paint": {"background-color": BACKGROUND_COLORS[variant]},
    }


def build_style(
    variant: str,
    tile_set: TileSet,
    *,
    center: Sequence[float] | None = None,
    zoom: float | None = None,
) -> dict:
    """构建单个 MapLibre style。

    ``center`` / ``zoom`` 只有静态托管版才写：MapLibre 在 ``style.load`` 且
    相机未被移动过时用它们做初始视野（桌面端有效，Immich 移动端不读）。
    """
    if variant not in VARIANTS:
        raise ValueError(f"未知样式变体: {variant!r}（可选 {', '.join(VARIANTS)}）")

    style: dict = {
        "version": 8,
        "name": display_name(variant, tile_set),
    }
    if center is not None and zoom is not None:
        style["center"] = [float(center[0]), float(center[1])]
        style["zoom"] = float(zoom)

    sources: dict = {}
    layers: list = [_background_layer(variant)]

    if variant == "sat":
        sources["sat"] = raster_source(tile_set.satellite())
        sources["lab"] = raster_source(tile_set.satellite_labels())
        layers.append({"id": "sat", "type": "raster", "source": "sat"})
        layers.append({"id": "lab", "type": "raster", "source": "lab"})
    else:
        sources["amap"] = raster_source(tile_set.road())
        layer: dict = {"id": "amap", "type": "raster", "source": "amap"}
        if variant == "dark":
            layer["paint"] = dict(DARK_ROAD_PAINT)
        layers.append(layer)

    style["sources"] = sources
    style["layers"] = layers
    return style


def build_style_set(tile_set: TileSet, **kwargs) -> dict[str, dict]:
    """构建 3 个变体，键为 :func:`style_name`（如 ``amap-fixed-light``）。"""
    styles = {}
    for variant in VARIANTS:
        styles[style_name(variant, tile_set)] = build_style(variant, tile_set, **kwargs)
    return styles


def build_compact_style(tile_set: TileSet, *, dark: bool) -> dict:
    """极简样式：单个瓦片域名、无背景层、无 attribution，``data:`` URL 最短。

    只为「不想部署任何东西、能贴就行」的场景提供；功能上等价于对应变体的
    简化版（没有背景色，瓦片缺失时会露底）。
    """
    source = raster_source(tile_set.road()[:1], attribution=None)
    layer: dict = {"id": "amap", "type": "raster", "source": "amap"}
    if dark:
        layer["paint"] = dict(DARK_ROAD_PAINT)
    return {
        "version": 8,
        "sources": {"amap": source},
        "layers": [layer],
    }


def build_compact_set(tile_set: TileSet) -> dict[str, dict]:
    """极简版的亮/暗两个变体，键为 ``compact-light`` / ``compact-dark``。"""
    return {
        "compact-light": build_compact_style(tile_set, dark=False),
        "compact-dark": build_compact_style(tile_set, dark=True),
    }
