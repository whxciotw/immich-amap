"""生成可直接粘贴进 Immich 的 ``data:`` URL 版样式（桌面端）。

对应改造前的根目录 ``build.py``。产物默认写到仓库的 ``dist/``：

- ``amap-{light,dark,sat}.json``          直连高德（不纠偏）
- ``amap-fixed-{light,dark,sat}.json``    经 tile-proxy 逐瓦片重采样纠偏
- ``urls.txt``                            所有 ``data:`` URL，一行一条
- ``--compact`` 时额外输出 ``compact-{light,dark}.json`` 与 ``urls-compact.txt``

.. warning::

   ``data:`` URL 在桌面浏览器里可用，但 Immich 移动端（``maplibre_gl``）不认，
   会黑屏。手机端请用 ``immich_amap.static`` 生成 http 托管版，见 ``docs/mobile.md``。
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from . import styles, urls
from .tiles import TileSet


def repo_root() -> pathlib.Path:
    """仓库根目录（源码运行时可用；``--out`` 可覆盖）。"""
    return pathlib.Path(__file__).resolve().parents[1]


def collect_styles(tile_base: str, *, include_raw: bool = True) -> dict[str, dict]:
    """收集全部 data: 样式。

    返回 ``{样式名: style dict}``，样式名即输出文件名（不含 ``.json``）。
    不带 ``fixed`` 的直连高德（不纠偏），带 ``fixed`` 的走 ``tile_base`` 纠偏。
    """
    result: dict[str, dict] = {}
    if include_raw:
        result.update(styles.build_style_set(TileSet(None)))
    result.update(styles.build_style_set(TileSet(tile_base)))
    return result


def urls_text(style_map: dict[str, dict], *, tile_base: str, percent: bool, compact: bool = False) -> str:
    """生成 ``urls.txt`` / ``urls-compact.txt`` 的文本内容。"""
    if compact:
        lines = [
            "# Immich 高德地图样式 —— 极简版 data: URL 清单",
            "# 直连高德，无需部署任何服务；只有亮/暗两套（单瓦片域名、无背景层，URL 最短）",
            "# 生成命令: python3 -m immich_amap urls --compact",
            "# 用法: Immich（管理员）→ 系统设置 → 地图与 GPS 设置 → 地图 → 亮色风格 / 暗色风格",
            "",
        ]
    else:
        lines = [
            "# Immich 高德地图样式 —— data: URL 清单",
            f"# 纠偏瓦片基址: {tile_base}",
            f"# 生成命令: python3 -m immich_amap urls --tile-base {tile_base}",
            "# 用法: Immich（管理员）→ 系统设置 → 地图与 GPS 设置 → 地图",
            "#       亮色风格 / 暗色风格 各粘贴一整行（以 data: 开头的那一行）",
            "# 注意: 带 fixed 的是纠偏版（照片坐标按 WGS-84 显示才对得上），不带的不纠偏。",
            "",
        ]
    for name, style in style_map.items():
        url = urls.encode_data_url(style, percent=percent)
        lines.append(f"## {name}  ({len(url)} 字符)")
        lines.append(url)
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="immich_amap urls",
        description="生成 data: URL 版 MapLibre 样式（桌面端直接粘贴用）",
    )
    parser.add_argument(
        "--tile-base",
        required=True,
        help="纠偏瓦片服务基址（例如 http://192.0.2.10:9002）",
    )
    parser.add_argument("--percent", action="store_true", help="输出 percent-encoded data URL（可读、可手改）")
    parser.add_argument("--emit-json", action="store_true", help="只写样式 JSON，不生成 urls.txt")
    parser.add_argument("--compact", action="store_true", help="额外生成极简版（单域名、无背景层，URL 最短）")
    parser.add_argument("--out", type=pathlib.Path, default=None, help="输出目录（默认 <仓库>/dist）")
    args = parser.parse_args(argv)

    out = args.out or (repo_root() / "dist")
    out.mkdir(parents=True, exist_ok=True)

    style_map = collect_styles(args.tile_base)
    for name, style in style_map.items():
        path = out / f"{name}.json"
        path.write_text(styles.json_dumps(style) + "\n", encoding="utf-8")
        url = urls.encode_data_url(style, percent=args.percent)
        print(f"{name:20s} json={len(styles.json_dumps(style)):5d}B  data-url={len(url):5d}字符 -> {path}")

    if args.compact:
        compact = styles.build_compact_set(TileSet(None))
        for name, style in compact.items():
            path = out / f"{name}.json"
            path.write_text(styles.json_dumps(style) + "\n", encoding="utf-8")
            url = urls.encode_data_url(style, percent=args.percent)
            print(f"{name:20s} json={len(styles.json_dumps(style)):5d}B  data-url={len(url):5d}字符 -> {path}")
        (out / "urls-compact.txt").write_text(
            urls_text(compact, tile_base="", percent=args.percent, compact=True),
            encoding="utf-8",
        )
        print(f"写入 {out / 'urls-compact.txt'}")

    if not args.emit_json:
        text = urls_text(style_map, tile_base=args.tile_base, percent=args.percent)
        (out / "urls.txt").write_text(text, encoding="utf-8")
        print(f"\n写入 {out / 'urls.txt'}")

    print("推荐组合：亮色=amap-fixed-light，暗色=amap-fixed-dark（或 amap-fixed-sat）")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
