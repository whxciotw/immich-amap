"""瓦片地址构造测试。"""

from __future__ import annotations

import urllib.parse

import pytest

from immich_amap import tiles


def test_direct_tiles_are_plain_amap_urls():
    tile_set = tiles.TileSet()
    assert not tile_set.fixed

    road = tile_set.road()
    assert len(road) == 4
    assert road[0] == (
        "https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
    )
    assert road[3].startswith("https://webrd04.is.autonavi.com/")


def test_satellite_tiles_use_webst_hosts_and_two_queries():
    tile_set = tiles.TileSet()
    images = tile_set.satellite()
    labels = tile_set.satellite_labels()

    assert len(images) == len(labels) == 4
    assert images[0] == "https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}"
    assert labels[0] == "https://webst01.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}"


def test_proxied_tiles_keep_placeholders_and_encode_upstream():
    tile_set = tiles.TileSet("http://192.0.2.10:9002")
    fixed = tile_set.fixed
    assert fixed

    url = tile_set.road()[0]
    assert url.startswith("http://192.0.2.10:9002/proxy/gcj2wgs/https%3A%2F%2Fwebrd01.is.autonavi.com%2F")
    # MapLibre 需要字面量 {x}/{y}/{z}，不能是 %7B%7D
    assert "{x}" in url and "{y}" in url and "{z}" in url
    assert "%7B" not in url and "%7D" not in url

    # 反解出来应正好是直连版的上游地址
    upstream = urllib.parse.unquote(url.split(tiles.PROXY_ROUTE, 1)[1])
    assert upstream == tiles.TileSet().road()[0]


def test_tile_base_trailing_slash_is_normalized():
    with_slash = tiles.TileSet("http://host:9002/")
    without = tiles.TileSet("http://host:9002")
    assert with_slash.road() == without.road()


def test_proxy_url_is_idempotent_for_query_separators():
    url = tiles.proxy_url("http://host:9002", "https://h/appmaptile?style=6&x={x}&y={y}&z={z}")
    assert url.count("?") == 0  # 上游的 ? 已被编码进路径参数
    assert "&" not in url


def test_unknown_tile_base_never_silently_corrupts_scheme():
    tile_set = tiles.TileSet("https://proxy.example.com/tiles")
    assert tile_set.road()[0].startswith("https://proxy.example.com/tiles/proxy/gcj2wgs/")


@pytest.mark.parametrize("key", ["roadHosts", "satelliteHosts", "roadQuery", "proxyRoute", "minZoom", "maxZoom"])
def test_tile_config_exposes_maker_html_keys(key):
    assert key in tiles.tile_config()
