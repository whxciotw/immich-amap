"""离线预览：按 Immich 的「25km 内最近点」规则，模拟一批坐标会显示成什么地名。

用途：

- **不碰 Immich** 就能对比不同 ``--level/--prefix`` 档位的实际展示效果；
- 拿真实资产坐标（CSV）统计「村镇名 / 英文名 / 只剩国家」的比例。

Immich 的逆地理编码逻辑（见 `map.repository.ts`）：在 ``geodata_places`` 里找
**25km 内最近的一行**，取它的 ``name`` 作为 city，``admin1`` 对应的名字作为 state，
``country`` 码经国家名表转成 country。本工具复刻这个规则，只读生成好的 geodata 目录。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections import Counter

from .geodata import Grid
from .geodata_amap import read_coords

#: 与 Immich 一致的搜索半径（km）
IMMICH_RADIUS_KM = 25.0

#: 会被统计成「村镇样」的名字后缀
VILLAGE_SUFFIXES: tuple[str, ...] = ("镇", "乡", "村", "街道", "屯")


def _load_rows(src: pathlib.Path) -> list[dict]:
    """读 ``cities500.txt``，只保留 Immich 需要的字段。"""
    items: list[dict] = []
    with open(src / "cities500.txt", encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 15:
                continue
            try:
                population = int(parts[14] or 0)
                latitude = float(parts[4])
                longitude = float(parts[5])
            except ValueError:
                continue  # 坏行跳过，预览工具不应该因一行脏数据崩掉
            items.append(
                {
                    "name": parts[1],
                    "lat": latitude,
                    "lon": longitude,
                    "code": parts[7],
                    "cc": parts[8],
                    "a1": parts[10],
                    "pop": population,
                }
            )
    return items


def _load_admin1(src: pathlib.Path) -> dict[str, str]:
    names: dict[str, str] = {}
    with open(src / "admin1CodesASCII.txt", encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\r\n").split("\t")
            if len(fields) > 1 and fields[0]:
                names[fields[0]] = fields[1]
    return names


def _load_country(src: pathlib.Path) -> dict[str, str]:
    names: dict[str, str] = {}
    with open(src / "countryInfo.txt", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            fields = line.rstrip("\r\n").split("\t")
            if len(fields) > 4:
                names[fields[0]] = fields[4]
    return names


def simulate(
    src: pathlib.Path,
    coords: list[tuple[float, float]],
    *,
    radius_km: float = IMMICH_RADIUS_KM,
) -> list[dict]:
    """对每个坐标返回 Immich 会显示的 ``city/state/country``。"""
    items = _load_rows(src)
    admin1_names = _load_admin1(src)
    country_names = _load_country(src)

    grid = Grid()
    for item in items:
        grid.add(item)

    results: list[dict] = []
    for lat, lon in coords:
        hit = grid.nearest(lat, lon, radius_km)
        if hit is None:
            results.append({"lat": lat, "lon": lon, "city": "", "state": "", "country": ""})
            continue
        results.append(
            {
                "lat": lat,
                "lon": lon,
                "city": hit["name"],
                "state": admin1_names.get(f"{hit['cc']}.{hit['a1']}", ""),
                "country": country_names.get(hit["cc"], ""),
            }
        )
    return results


def _is_english(name: str) -> bool:
    return bool(name) and not any("\u4e00" <= char <= "\u9fff" for char in name)


def _is_village(name: str) -> bool:
    return name.endswith(VILLAGE_SUFFIXES)


def summarize(results: list[dict]) -> dict:
    """汇总指标（同时供测试/CLI 使用）。"""
    total = len(results)
    with_city = [row for row in results if row["city"]]
    only_country = total - len(with_city)
    english = sum(1 for row in with_city if _is_english(row["city"]))
    village = sum(1 for row in with_city if _is_village(row["city"]))
    top = Counter(row["city"] for row in with_city).most_common(10)
    return {
        "total": total,
        "with_city": len(with_city),
        "only_country": only_country,
        "english": english,
        "village": village,
        "top": top,
    }


def _format_summary(summary: dict, title: str) -> str:
    lines = [
        f"== {title}: {summary['total']} 个坐标",
        f"   有城市名 : {summary['with_city']}"
        f"（{summary['with_city'] / summary['total'] * 100:.1f}%）" if summary["total"] else "   有城市名 : 0",
        f"   村镇样   : {summary['village']}",
        f"   英文名   : {summary['english']}",
        f"   只剩国家 : {summary['only_country']}",
        "   TOP: " + " · ".join(f"{name}×{count}" for name, count in summary["top"][:5]),
    ]
    return "\n".join(lines)


def _print_diff(before: list[dict], after: list[dict]) -> None:
    changed = [
        (old, new)
        for old, new in zip(before, after)
        if (old["city"], old["state"], old["country"]) != (new["city"], new["state"], new["country"])
    ]
    print(f"== 两档差异：{len(changed)}/{len(before)} 个坐标显示会变")
    for old, new in changed[:15]:
        before_text = ", ".join(part for part in (old["city"], old["state"], old["country"]) if part) or "(无)"
        after_text = ", ".join(part for part in (new["city"], new["state"], new["country"]) if part) or "(无)"
        print(f"   {old['lat']:.4f},{old['lon']:.4f}: {before_text} → {after_text}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="immich-amap geodata-sim",
        description="按 Immich 的 25km 最近点规则，离线预览一批坐标会显示成什么地名",
    )
    parser.add_argument("--src", type=pathlib.Path, required=True, help="生成好的 geodata 目录")
    parser.add_argument(
        "--coords",
        type=pathlib.Path,
        required=True,
        help="坐标 CSV（latitude,longitude 表头或 lat,lon 两列）",
    )
    parser.add_argument("--radius", type=float, default=IMMICH_RADIUS_KM, help="搜索半径 km（默认 25，与 Immich 一致）")
    parser.add_argument("--limit", type=int, help="最多模拟多少个坐标")
    parser.add_argument("--compare", type=pathlib.Path, help="另一份 geodata 目录，输出两档差异")
    args = parser.parse_args(argv)

    missing = [
        name
        for name in ("cities500.txt", "admin1CodesASCII.txt", "countryInfo.txt")
        if not (args.src / name).is_file()
    ]
    if missing:
        parser.error(f"{args.src} 缺少文件: {', '.join(missing)}")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit 必须大于 0")
    if not (0 < args.radius <= 1000):
        parser.error("--radius 必须在 (0, 1000] 之间")
    coords = read_coords(args.coords)
    if not coords:
        parser.error(f"{args.coords} 里没有读到坐标")
    if args.limit:
        coords = coords[: args.limit]

    results = simulate(args.src, coords, radius_km=args.radius)
    print(_format_summary(summarize(results), str(args.src)))

    if args.compare:
        missing_compare = [
            name
            for name in ("cities500.txt", "admin1CodesASCII.txt", "countryInfo.txt")
            if not (args.compare / name).is_file()
        ]
        if missing_compare:
            parser.error(f"{args.compare} 缺少文件: {', '.join(missing_compare)}")
        other = simulate(args.compare, coords, radius_km=args.radius)
        print(_format_summary(summarize(other), str(args.compare)))
        _print_diff(results, other)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
