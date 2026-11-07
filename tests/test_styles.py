"""MapLibre style 构建测试。"""

from __future__ import annotations

import pytest

from immich_amap import build, styles
from immich_amap.tiles import PROXY_ROUTE, TileSet


@pytest.fixture()
def raw() -> TileSet:
    return TileSet()


@pytest.fixture()
def fixed() -> TileSet:
    return TileSet("http://192.0.2.10:9002")


@pytest.mark.parametrize("variant", styles.VARIANTS)
def test_style_has_valid_skeleton(variant, raw):
    style = styles.build_style(variant, raw)

    assert style["version"] == 8
    assert style["name"]
    source_ids = set(style["sources"])
    assert source_ids, "必须有 source"
    for layer in style["layers"]:
        if layer["type"] == "raster":
            assert layer["source"] in source_ids
    for source in style["sources"].values():
        assert source["type"] == "raster"
        assert source["tileSize"] == 256
        assert source["minzoom"] == 3
        assert source["maxzoom"] == 18
        assert source["tiles"], "tiles 不能为空"


def test_light_style_has_background_and_one_raster(raw):
    style = styles.build_style("light", raw)
    assert [layer["type"] for layer in style["layers"]] == ["background", "raster"]
    assert style["layers"][0]["paint"]["background-color"] == styles.BACKGROUND_COLORS["light"]


def test_dark_style_applies_raster_filters(raw):
    style = styles.build_style("dark", raw)
    raster = style["layers"][1]
    assert raster["paint"] == dict(styles.DARK_ROAD_PAINT)


def test_satellite_style_layers_two_sources(raw):
    style = styles.build_style("sat", raw)
    assert set(style["sources"]) == {"sat", "lab"}
    assert [layer["id"] for layer in style["layers"]] == ["bg", "sat", "lab"]


def test_fixed_uses_proxied_tiles(fixed):
    for variant in styles.VARIANTS:
        style = styles.build_style(variant, fixed)
        for source in style["sources"].values():
            assert all(PROXY_ROUTE in url for url in source["tiles"])


def test_raw_has_no_proxy(raw):
    for variant in styles.VARIANTS:
        style = styles.build_style(variant, raw)
        assert all(PROXY_ROUTE not in url for source in style["sources"].values() for url in source["tiles"])


def test_static_style_carries_center_and_zoom(raw):
    style = styles.build_style("light", raw, center=(121.4737, 31.2304), zoom=15)
    assert style["center"] == [121.4737, 31.2304]
    assert style["zoom"] == 15.0


def test_data_url_style_has_no_center(raw):
    assert "center" not in styles.build_style("light", raw)


def test_style_name_matches_output_file_names(raw, fixed):
    assert styles.style_name("light", raw) == "amap-light"
    assert styles.style_name("sat", raw) == "amap-sat"
    assert styles.style_name("light", fixed) == "amap-fixed-light"
    assert styles.style_name("sat", fixed) == "amap-fixed-sat"


def test_invalid_variant_raises(raw):
    with pytest.raises(ValueError):
        styles.build_style("terrain", raw)


def test_build_style_set_covers_all_variants(raw):
    style_set = styles.build_style_set(raw)
    assert set(style_set) == {"amap-light", "amap-dark", "amap-sat"}


def test_compact_style_is_minimal(raw):
    style = styles.build_compact_style(raw, dark=False)
    assert "name" not in style
    assert "attribution" not in style["sources"]["amap"]
    assert len(style["sources"]["amap"]["tiles"]) == 1
    assert [layer["type"] for layer in style["layers"]] == ["raster"]
    assert "paint" not in style["layers"][0]


def test_compact_dark_applies_filters(raw):
    style = styles.build_compact_style(raw, dark=True)
    assert style["layers"][0]["paint"] == dict(styles.DARK_ROAD_PAINT)


def test_collect_styles_builds_six_data_url_variants():
    style_map = build.collect_styles("http://192.0.2.10:9002")
    assert set(style_map) == {
        "amap-light",
        "amap-dark",
        "amap-sat",
        "amap-fixed-light",
        "amap-fixed-dark",
        "amap-fixed-sat",
    }
