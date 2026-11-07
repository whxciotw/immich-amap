"""``data:`` URL 编解码。

Immich 的样式设置只校验「是不是合法 URL」，而 ``data:application/json;base64,...``
本身就是合法 URL（``new URL()`` 接受任意 scheme）；MapLibre 的 ``makeRequest()``
对不含 ``://`` 的地址直接走 ``fetch()``，``data:`` 正好命中。于是可以把
整个 style.json 塞进一条 URL 直接粘贴，省掉找地方托管 JSON。

.. note::

   ``data:`` URL 只在桌面浏览器里可用。Immich 移动端用 ``maplibre_gl`` 的
   ``styleString``，原生层会把 ``data:`` 当成 Flutter asset 路径 → 加载失败 →
   地图黑屏。手机端必须用 http(s) 托管，见 ``docs/mobile.md``。
"""

from __future__ import annotations

import base64
import json
import urllib.parse
from collections.abc import Mapping
from typing import Any


def dumps(style: Mapping[str, Any]) -> str:
    """紧凑 JSON（与写盘用的缩进格式无关，只影响 URL 长度）。"""
    return json.dumps(style, ensure_ascii=False, separators=(",", ":"))


def encode_data_url(style: Mapping[str, Any], *, percent: bool = False) -> str:
    """把 style 编码成可粘贴的 ``data:`` URL。

    :param percent: ``True`` 输出 percent-encoding（可读、可手改，但更长）；
        默认输出 base64。
    """
    raw = dumps(style)
    if percent:
        return "data:application/json," + urllib.parse.quote(raw, safe="")
    return "data:application/json;base64," + base64.b64encode(raw.encode("utf-8")).decode("ascii")


def decode_data_url(url: str) -> dict:
    """``encode_data_url`` 的逆操作（selftest 用）。"""
    header, sep, body = url.partition(",")
    if not sep or not header.startswith("data:"):
        raise ValueError("不是 data: URL")
    if header.endswith(";base64"):
        return json.loads(base64.b64decode(body).decode("utf-8"))
    return json.loads(urllib.parse.unquote(body))


def is_data_url(url: str) -> bool:
    return url.startswith("data:")
