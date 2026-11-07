"""命令行入口：``python3 -m immich_amap <子命令>``。

子命令：

============================  ===============================================
``urls``                      生成 data: URL 版样式（桌面端直接粘贴）
``static``                    生成 http 静态托管版样式（桌面 + 手机端）
``selftest``                  端到端抓图自测
``geodata``                   改造 Immich 的中文 / 可控粒度地名库
``amap-cache``                用高德反查生成精修缓存（可选，主流程不联网）
``geodata-sim``               离线预览坐标会显示成什么地名（不碰 Immich）
============================  ===============================================

安装后（``pip install -e .``）也可以直接用 ``immich-amap <子命令>``。
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Optional

from . import __version__, build, geodata, geodata_amap, geodata_sim, selftest, static

Subcommand = Callable[[Optional[list[str]]], int]

SUBCOMMANDS: dict[str, Subcommand] = {
    "urls": build.main,
    "static": static.main,
    "selftest": selftest.main,
    "geodata": geodata.main,
    "amap-cache": geodata_amap.main,
    "geodata-sim": geodata_sim.main,
}

DESCRIPTIONS = {
    "urls": "生成 data: URL 版样式（桌面端直接粘贴进 Immich）",
    "static": "生成静态托管版样式（桌面 + 手机端，需要 nginx 之类）",
    "selftest": "端到端抓图自测：验证样式里的瓦片地址能否出图",
    "geodata": "把 Immich 的 GeoNames 地名库改造成「中文 + 可控粒度」",
    "amap-cache": "用高德反查生成地名精修缓存（可选，主流程不联网）",
    "geodata-sim": "离线预览一批坐标在 Immich 里会显示成什么地名",
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(
        prog="immich-amap",
        description="Immich 高德地图（GCJ-02 纠偏）样式与中文地名库工具",
        epilog="子命令用法：python3 -m immich_amap <子命令> --help",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("command", nargs="?", choices=list(SUBCOMMANDS), help="子命令")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="子命令参数")

    ns = parser.parse_args(argv)
    if not ns.command:
        parser.print_help()
        return 0

    print(f"== {ns.command}: {DESCRIPTIONS[ns.command]}", file=sys.stderr)
    return SUBCOMMANDS[ns.command](ns.args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
