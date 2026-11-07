"""``data:`` URL 编解码测试。"""

from __future__ import annotations

import pytest

from immich_amap import urls

STYLE = {"version": 8, "name": "高德路网", "sources": {"a": {"tiles": ["https://x/{x}/{y}/{z}"]}}, "layers": []}


def test_base64_roundtrip_preserves_unicode():
    encoded = urls.encode_data_url(STYLE)
    assert encoded.startswith("data:application/json;base64,")
    assert urls.decode_data_url(encoded) == STYLE


def test_percent_roundtrip():
    encoded = urls.encode_data_url(STYLE, percent=True)
    assert encoded.startswith("data:application/json,")
    assert urls.decode_data_url(encoded) == STYLE


def test_base64_is_shorter_than_percent_for_chinese():
    base64_url = urls.encode_data_url(STYLE)
    percent_url = urls.encode_data_url(STYLE, percent=True)
    assert len(base64_url) < len(percent_url)


def test_is_data_url():
    assert urls.is_data_url(urls.encode_data_url(STYLE))
    assert not urls.is_data_url("https://example.com/style.json")


@pytest.mark.parametrize("bad", ["https://example.com/style.json", "data:application/json;base64,###"])
def test_decode_rejects_non_data_url_or_bad_payload(bad):
    with pytest.raises(ValueError):
        urls.decode_data_url(bad)


def test_dumps_is_compact_and_keeps_unicode():
    text = urls.dumps(STYLE)
    assert " " not in text
    assert "高德路网" in text
