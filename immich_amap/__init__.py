"""Immich 高德地图（GCJ-02 纠偏）样式与中文地名库工具。

对外主要 API：

- :mod:`immich_amap.tiles` —— 高德栅格瓦片地址（直连 / 经 tile-proxy 纠偏）
- :mod:`immich_amap.styles` —— MapLibre style 构建
- :mod:`immich_amap.urls` —— ``data:`` URL 编解码

命令行用法见 ``python3 -m immich_amap --help``。
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
