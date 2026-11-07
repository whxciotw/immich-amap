"""``web/maker.html`` 与 Python 侧的瓦片配置一致性测试。

maker.html 是纯前端、离线可用的生成器，必然重复一份瓦片常量；
本测试保证它不会和 :func:`immich_amap.tiles.tile_config` 漂移。
"""

from __future__ import annotations

import json
import pathlib
import re

from immich_amap import tiles

MAKER_HTML = pathlib.Path(__file__).resolve().parents[1] / "web" / "maker.html"


def load_maker_config() -> dict:
    text = MAKER_HTML.read_text(encoding="utf-8")
    match = re.search(r"const TILE_CONFIG = (\{.*?\n\});", text, re.S)
    assert match, "maker.html 里找不到 TILE_CONFIG"
    return json.loads(match.group(1))


def test_maker_html_exists():
    assert MAKER_HTML.is_file()


def test_maker_config_matches_python():
    assert load_maker_config() == tiles.tile_config()


def test_maker_html_uses_proxy_route_constant():
    text = MAKER_HTML.read_text(encoding="utf-8")
    assert "TILE_CONFIG.proxyRoute" in text
    assert "proxy/gcj2wgs/" in text


def test_maker_html_mentions_mobile_limitation():
    text = MAKER_HTML.read_text(encoding="utf-8")
    assert "移动端" in text and "data:" in text
