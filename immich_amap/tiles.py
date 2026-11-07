"""高德栅格瓦片地址：直连（不纠偏）或经 ``tile-proxy`` 纠偏。

高德有两类栅格瓦片，都走 ``appmaptile`` 接口：

- 路网 / 注记：``webrd0{1..4}.is.autonavi.com``，``style=8``（带中文注记）
- 卫星影像：``webst0{1..4}.is.autonavi.com``，``style=6``；
  卫星注记同样是 ``style=8`` 的透明图层，叠加在影像上

高德瓦片使用 **GCJ-02**（火星坐标）网格，而照片 EXIF 里的 GPS 通常是 **WGS-84**。
纠偏版把「上游高德 URL」编码成 ``tile-proxy`` 的路径参数
（``/proxy/gcj2wgs/<urlencoded upstream url>``），由代理把 WGS-84 网格换算成
GCJ-02、抓取 1~4 张上游瓦片重采样后输出 256x256 的图。

本模块是瓦片地址的唯一事实来源。``web/maker.html`` 内嵌的 ``TILE_CONFIG``
必须与本模块的 :func:`tile_config` 一致，由 ``tests/test_web.py`` 校验。
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass

# ---- 高德上游 ------------------------------------------------------------
ROAD_HOSTS: tuple[str, ...] = tuple(f"webrd0{i}.is.autonavi.com" for i in (1, 2, 3, 4))
SATELLITE_HOSTS: tuple[str, ...] = tuple(f"webst0{i}.is.autonavi.com" for i in (1, 2, 3, 4))

ROAD_QUERY = "lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
SATELLITE_IMAGE_QUERY = "style=6&x={x}&y={y}&z={z}"
SATELLITE_LABEL_QUERY = "style=8&x={x}&y={y}&z={z}"

MIN_ZOOM = 3
MAX_ZOOM = 18  # 高德 z>=19 不再出图，再放大只是拉伸
ATTRIBUTION = "© 高德地图 AutoNavi"

# ---- 纠偏代理 ------------------------------------------------------------
PROXY_ROUTE = "/proxy/gcj2wgs/"


def upstream_url(host: str, query: str) -> str:
    """拼一条上游高德瓦片模板（``{x}``/``{y}``/``{z}`` 原样保留）。"""
    return f"https://{host}/appmaptile?{query}"


def proxy_url(tile_base: str, upstream: str) -> str:
    """把上游瓦片模板包装成 ``tile-proxy`` 纠偏地址。

    ``safe="{}"`` 很关键：它保住 ``{x}/{y}/{z}`` 字面量，MapLibre 才能做
    瓦片坐标替换；其余字符（``:``、``/``、``?``、``&``、``=``）全部百分号编码。
    """
    return tile_base.rstrip("/") + PROXY_ROUTE + urllib.parse.quote(upstream, safe="{}")


@dataclass(frozen=True)
class TileSet:
    """一组瓦片模板。

    ``tile_base`` 为空表示直连高德（不纠偏）；给出 ``tile-proxy`` 的基址
    （例如 ``http://192.0.2.10:9002``）表示走逐瓦片纠偏。
    """

    tile_base: str | None = None

    @property
    def fixed(self) -> bool:
        """是否走纠偏代理。"""
        return self.tile_base is not None

    def _build(self, query: str, hosts: Sequence[str]) -> list[str]:
        upstreams = [upstream_url(host, query) for host in hosts]
        if self.tile_base is None:
            return upstreams
        return [proxy_url(self.tile_base, url) for url in upstreams]

    def road(self) -> list[str]:
        """路网 + 注记。"""
        return self._build(ROAD_QUERY, ROAD_HOSTS)

    def satellite(self) -> list[str]:
        """卫星影像。"""
        return self._build(SATELLITE_IMAGE_QUERY, SATELLITE_HOSTS)

    def satellite_labels(self) -> list[str]:
        """卫星影像上的路网注记（透明图层）。"""
        return self._build(SATELLITE_LABEL_QUERY, SATELLITE_HOSTS)


def tile_config() -> dict:
    """供 ``web/maker.html`` 内嵌的 ``TILE_CONFIG`` 使用的配置快照。"""
    return {
        "roadHosts": list(ROAD_HOSTS),
        "satelliteHosts": list(SATELLITE_HOSTS),
        "roadQuery": ROAD_QUERY,
        "satelliteImageQuery": SATELLITE_IMAGE_QUERY,
        "satelliteLabelQuery": SATELLITE_LABEL_QUERY,
        "proxyRoute": PROXY_ROUTE,
        "minZoom": MIN_ZOOM,
        "maxZoom": MAX_ZOOM,
        "attribution": ATTRIBUTION,
    }
