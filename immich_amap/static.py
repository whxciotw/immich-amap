"""生成「静态托管版」样式（nginx 等静态服务用，桌面端 + 手机端都可用）。

对应改造前的根目录 ``make_static.py``。和 :mod:`immich_amap.build`（``data:`` URL）
的区别：

1. 输出是可直接丢给 nginx 的 ``style-*.json``；
2. 额外写入 ``center`` / ``zoom``（桌面端初始视野，Immich 移动端不读）。

为什么必须用 http 托管：Immich 移动端用 ``maplibre_gl`` 的 ``styleString``，
原生层只接受 http(s) URL 或内联 JSON，``data:`` 会被当成 Flutter asset 路径，
导致地图黑屏。见 ``docs/mobile.md``。
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from . import styles
from .tiles import TileSet

#: 默认初始视野：北京天安门（中性示例，实际请换成自己的常用地点）
DEFAULT_CENTER = (116.3975, 39.909)
DEFAULT_ZOOM = 5.0

#: 输出文件名 → 样式变体
STYLE_FILES: dict[str, str] = {
    "style-light.json": "light",
    "style-dark.json": "dark",
    "style-sat.json": "sat",
}


def parse_center(text: str) -> tuple[float, float]:
    """解析 ``经度,纬度``。"""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"坐标格式应为「经度,纬度」: {text!r}")
    try:
        lng, lat = (float(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"坐标不是数字: {text!r}") from exc
    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
        raise argparse.ArgumentTypeError(f"坐标超出范围: {text!r}")
    return lng, lat


def collect_styles(
    tile_set: TileSet,
    *,
    center: tuple[float, float] = DEFAULT_CENTER,
    zoom: float = DEFAULT_ZOOM,
) -> dict[str, dict]:
    """生成 3 个静态样式文件（文件名 → style dict）。"""
    return {
        filename: styles.build_style(variant, tile_set, center=center, zoom=zoom)
        for filename, variant in STYLE_FILES.items()
    }


def urls_text(public_base: str, style_names: list[str]) -> str:
    """生成「粘贴到 Immich 的 http 地址」清单。"""
    base = public_base.rstrip("/")
    return "\n".join(
        [
            "# Immich 地图样式（http 托管版：桌面端 + 手机端都能用）",
            "# 生成命令: python3 -m immich_amap static --tile-base <tile-proxy 地址> --public-base <样式服务对外地址>",
            "",
            "# 亮色风格：",
            f"{base}/{style_names[0]}",
            "",
            "# 暗色风格：",
            f"{base}/{style_names[1]}",
            "",
            "# 备选（卫星影像 + 路网注记，亮/暗都能用）：",
            f"{base}/{style_names[2]}",
            "",
            "# 改初始视野：编辑 style-*.json 的 center / zoom，保存后刷新页面即可",
            "#（样式服务设了 Cache-Control: no-cache，不用重启容器）。",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="immich_amap static",
        description="生成 http 静态托管版 MapLibre 样式（桌面 + 手机端）",
    )
    parser.add_argument("--tile-base", required=True, help="纠偏瓦片服务基址，如 http://192.0.2.10:9002")
    parser.add_argument("--center", type=parse_center, default=DEFAULT_CENTER, help="初始视野「经度,纬度」")
    parser.add_argument("--zoom", type=float, default=DEFAULT_ZOOM, help="初始缩放级别")
    parser.add_argument("--out", type=pathlib.Path, default=None, help="输出目录（默认 <仓库>/dist/mapstyles）")
    parser.add_argument(
        "--public-base",
        default=None,
        help="样式服务的对外地址，给出时额外生成 urls.txt（如 http://192.0.2.10:9003）",
    )
    args = parser.parse_args(argv)

    out = args.out or pathlib.Path(__file__).resolve().parents[1] / "dist" / "mapstyles"
    out.mkdir(parents=True, exist_ok=True)

    tile_set = TileSet(args.tile_base)
    if not tile_set.fixed:  # pragma: no cover - required=True 已保证
        parser.error("--tile-base 不能为空")

    style_map = collect_styles(tile_set, center=args.center, zoom=args.zoom)
    for filename, style in style_map.items():
        path = out / filename
        path.write_text(styles.json_dumps(style) + "\n", encoding="utf-8")
        print(f"{filename:20s} center={list(args.center)} zoom={args.zoom}  -> {path}")

    if args.public_base:
        (out / "urls.txt").write_text(urls_text(args.public_base, list(style_map)), encoding="utf-8")
        print(f"写入 {out / 'urls.txt'}")

    print(f"\n部署：把 {out}/*.json 同步到样式服务的站点目录（容器内路径见 docs/deployment.md）")
    print("初始视野改动后刷新页面即可生效（nginx 设置了 Cache-Control: no-cache）")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
