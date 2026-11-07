"""新数据源与粒度参数化的单元测试（P0-1 / P0-2 / P1-1 / P2-1）。

全部用合成 fixture，不依赖真实 GeoNames 数据与网络。
"""

from __future__ import annotations

import json
import pathlib

import pytest

from immich_amap import geodata, geodata_amap, geodata_names

COUNTRY_HEADER = "# GeoNames countryInfo.txt\n# ISO\tISO3\tISO-Numeric\tfips\tCountry\tCapital\n"


def city_row(
    gid: str,
    name: str,
    alternates: str,
    lat: float,
    lon: float,
    fcode: str,
    cc: str,
    admin1: str,
    population: int,
    admin2: str = "",
) -> str:
    fields = [
        gid, name, name, alternates, lat, lon, "P", fcode, cc, "",
        admin1, admin2, "", "", population, "", "", "Asia/Shanghai", "2026-01-01",
    ]
    return "\t".join(str(field) for field in fields)


@pytest.fixture()
def geodata_src(tmp_path: pathlib.Path) -> pathlib.Path:
    src = tmp_path / "src"
    src.mkdir()

    (src / "countryInfo.txt").write_text(
        COUNTRY_HEADER
        + "CN\tCHN\t156\tCH\tChina\tBeijing\n"
        + "TH\tTHA\t764\tTH\tThailand\tBangkok\n"
        + "CL\tCHL\t152\tCI\tChile\tSantiago\n"
        + "HK\tHKG\t344\tHK\tHong Kong\tHong Kong\n"
        + "TW\tTWN\t158\tTW\tTaiwan\tTaipei\n"
        + "MO\tMAC\t446\tMO\tMacau\tMacau\n",
        encoding="utf-8",
    )
    (src / "admin1CodesASCII.txt").write_text(
        "CN.31\tShanghai\tShanghai\t1796236\n"
        "CN.24\tShanxi\tShanxi\t1795912\n"
        "CN.32\tJiangsu\tJiangsu\t1795913\n"
        "TH.40\tBangkok\tBangkok\t1609350\n"
        "HK.HC\tHong Kong\tHong Kong\t1819730\n",
        encoding="utf-8",
    )
    (src / "admin2Codes.txt").write_text("CN.31.01\tHuangpu\tHuangpu\t1800000\n", encoding="utf-8")
    (src / "ne_10m_admin_0_countries.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"ISO_A2": iso, "NAME_ZH": name}}
                    for iso, name in (
                        ("CN", "中国"),
                        ("TH", "泰国"),
                        ("CL", "智利"),
                        ("HK", "中国香港"),
                        ("TW", "中国台湾"),
                        ("MO", "中国澳门"),
                    )
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (src / "cities500.txt").write_text(
        "\n".join(
            [
                city_row("1796236", "Shanghai", "上海,上海市", 31.22222, 121.45806, "PPLA", "CN", "31", 24256800),
                city_row("1785603", "Linfen", "临汾,临汾市", 36.08889, 111.51889, "PPL", "CN", "24", 500000),
                city_row("1790645", "Kangqiao", "康桥镇", 31.15, 121.6, "PPL", "CN", "31", 100000),
                city_row("1609350", "Bangkok", "曼谷", 13.75, 100.5, "PPLC", "TH", "40", 5104476),
                # 没有中文别名 → 由 alternateNamesV2 补「芭达亚」
                city_row("1614295", "Pattaya", "Pattaya,พัทยา", 12.933, 100.883, "PPL", "TH", "40", 119532),
                city_row("1819729", "Hong Kong", "香港", 22.28, 114.17, "PPLC", "HK", "", 7482500),
                city_row("1668341", "Taipei", "台北,台北市", 25.05, 121.5, "PPLC", "TW", "", 7871900),
                city_row("1821274", "Macau", "澳门", 22.2, 113.54, "PPLC", "MO", "", 600000),
                city_row("9999999", "Somewhere", "某某", -33.0, -70.0, "PPL", "CL", "", 100),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return src


@pytest.fixture()
def enhance_dump(tmp_path: pathlib.Path) -> pathlib.Path:
    """模拟 GeoNames 的 CN.txt：含区县、乡镇、低人口、非 P 类、重复 id / 重复坐标。"""
    path = tmp_path / "CN.txt"
    path.write_text(
        "\n".join(
            [
                city_row("1790700", "Kunshan", "昆山,昆山市", 31.39, 120.98, "PPLA3", "CN", "32", 2000000),
                city_row("1790701", "Huaqiao", "花桥镇", 31.34, 121.10, "PPL", "CN", "32", 100000),
                city_row("1790702", "Xiaocun", "小村", 31.30, 121.10, "PPL", "CN", "31", 50),
                city_row("1790703", "Some Hill", "", 31.30, 121.10, "T", "CN", "31", 0),
                city_row("1796236", "Shanghai", "上海", 31.22222, 121.45806, "PPLA", "CN", "31", 24256800),
                city_row("1790704", "Dup Coord", "重复坐标", 31.15, 121.6, "PPL", "CN", "31", 999999),
                # 第 7 列是 T（山），不是 P 类，必须被过滤
                "\t".join(
                    ["1790705", "Mountain", "山", "", "31.0", "121.0", "T", "T", "CN", "", "31", "", "", "", "0"]
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def alternate_names(tmp_path: pathlib.Path) -> pathlib.Path:
    """模拟 alternateNamesV2.txt（10 列）。"""
    path = tmp_path / "alternateNamesV2.txt"
    path.write_text(
        "\n".join(
            [
                # 语言优先级：zh > zh-Hans；preferred 优先
                "1001\t1614295\tzh-Hans\t芭提雅\t0\t0\t0\t0\t\t",
                "1002\t1614295\tzh\t芭达亚\t1\t0\t0\t0\t\t",
                "1003\t1614295\tzh\t芭达亚\t0\t0\t0\t0\t\t",
                # 历史名/俗称必须被过滤
                "1004\t1614295\tzh\t暹罗旧称\t1\t0\t0\t1\t\t",
                "1005\t1614295\tzh\t俗称地\t1\t0\t1\t0\t\t",
                # 繁体 → 简体
                "1006\t1785603\tzh-Hant\t黃山市\t1\t0\t0\t0\t\t",
                # 非中文语言 / 非中文内容忽略
                "1007\t1609350\tja\tバンコク\t1\t0\t0\t0\t\t",
                "1008\t1609350\tzh\tBangkok\t1\t0\t0\t0\t\t",
                # 国家名过滤
                "1009\t1796236\tzh\t中国\t1\t0\t0\t0\t\t",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def amap_cache(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "amap-cache.csv"
    path.write_text(
        "geonameid,cc,lat,lon,admin1,admin2,admin3,admin4,fetched_at\n"
        "1790645,CN,31.15,121.6,上海市,,浦东新区,康桥镇,2026-11-07T00:00:00+00:00\n"
        "1819729,HK,22.28,114.17,香港特别行政区,,,,\n",
        encoding="utf-8",
    )
    return path


def read_cities(path: pathlib.Path) -> dict[str, list[str]]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        rows[fields[0]] = fields
    return rows


# --------------------------------------------------------------------------
# P0-1 增强点集
# --------------------------------------------------------------------------
def test_enhance_merges_filtered_rows(geodata_src, enhance_dump, tmp_path):
    dst = tmp_path / "out"
    stats = geodata.run(geodata_src, dst, enhance=[enhance_dump], quiet=True)
    rows = read_cities(dst / "cities500.txt")

    # 昆山 + 花桥镇 并入；小村人口 50、T 类、重复 id、重复坐标全部过滤
    assert stats["enhance_rows"] == 2
    assert "1790700" in rows and "1790701" in rows
    assert "1790702" not in rows and "1790703" not in rows and "1790704" not in rows


def test_enhance_full_ignores_population(geodata_src, enhance_dump, tmp_path):
    stats = geodata.run(geodata_src, tmp_path / "out", enhance=[enhance_dump], full=True, quiet=True)
    assert stats["enhance_rows"] == 3
    assert "1790702" in read_cities(tmp_path / "out" / "cities500.txt")


def test_enhance_default_keeps_row_count(geodata_src, tmp_path):
    stats = geodata.run(geodata_src, tmp_path / "out", quiet=True)
    assert stats["enhance_rows"] == 0
    assert stats["cities_total"] == 9


# --------------------------------------------------------------------------
# P0-2 全量中文别名
# --------------------------------------------------------------------------
def test_alternate_index_priority_and_filters(alternate_names, tmp_path):
    wanted = {"1614295", "1785603", "1609350", "1796236"}
    index = geodata_names.build_alternate_index(alternate_names, wanted)
    assert index["1614295"] == "芭达亚"  # zh + preferred 赢过 zh-Hans「芭提雅」
    assert index["1785603"] == "黄山市"  # 繁体转简体（内置 251 字表覆盖「黃」）
    assert "1609350" not in index  # 非中文内容被丢
    assert "1796236" not in index  # 「中国」被丢


def test_alternate_names_fill_missing_chinese(geodata_src, alternate_names, tmp_path):
    dst = tmp_path / "out"
    stats = geodata.run(geodata_src, dst, alternate_names=alternate_names, quiet=True)
    rows = read_cities(dst / "cities500.txt")

    assert stats["alternate_rows"] == 1
    assert rows["1614295"][1] == "泰国 · 芭达亚"


def test_alternate_names_do_not_override_amap(geodata_src, alternate_names, amap_cache, tmp_path):
    dst = tmp_path / "out"
    geodata.run(geodata_src, dst, alternate_names=alternate_names, amap_cache=amap_cache, quiet=True)
    rows = read_cities(dst / "cities500.txt")
    # 康桥镇在高德缓存里，别名源不应覆盖它
    assert rows["1790645"][1] == "上海市"


# --------------------------------------------------------------------------
# P1-1 高德缓存
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("city", "上海市"),
        ("county", "上海 · 浦东新区"),
        ("town", "上海 · 康桥镇"),
    ],
)
def test_amap_cache_applied_by_level(geodata_src, amap_cache, tmp_path, level, expected):
    dst = tmp_path / f"out-{level}"
    stats = geodata.run(geodata_src, dst, amap_cache=amap_cache, level=level, quiet=True)
    rows = read_cities(dst / "cities500.txt")
    assert stats["amap_rows"] >= 1
    assert rows["1790645"][1] == expected


def test_amap_cache_hk_special_admin_suffix(geodata_src, amap_cache, tmp_path):
    dst = tmp_path / "out"
    geodata.run(geodata_src, dst, amap_cache=amap_cache, quiet=True)
    rows = read_cities(dst / "cities500.txt")
    # 「香港特别行政区」收敛成「香港」，直辖市/特区不加前缀
    assert rows["1819729"][1] == "香港"


def test_load_amap_cache(amap_cache):
    cache = geodata_names.load_amap_cache(amap_cache)
    assert cache["1790645"]["admin3"] == "浦东新区"
    assert cache["1819729"]["admin1"] == "香港特别行政区"


# --------------------------------------------------------------------------
# P2-1 粒度与显示参数
# --------------------------------------------------------------------------
def test_prefix_none_keeps_plain_city_name(geodata_src, tmp_path):
    dst = tmp_path / "out"
    stats = geodata.run(geodata_src, dst, prefix="none", quiet=True)
    rows = read_cities(dst / "cities500.txt")
    assert rows["1785603"][1] == "临汾市"
    assert rows["1609350"][1] == "曼谷"
    assert stats["display_with_separator"] == 0


def test_custom_separator(geodata_src, tmp_path):
    dst = tmp_path / "out"
    geodata.run(geodata_src, dst, separator=" / ", quiet=True)
    rows = read_cities(dst / "cities500.txt")
    assert rows["1785603"][1] == "山西 / 临汾市"


def test_level_county_normalizes_to_county_anchor(geodata_src, enhance_dump, tmp_path):
    dst = tmp_path / "out"
    stats = geodata.run(geodata_src, dst, enhance=[enhance_dump], level="county", quiet=True)
    rows = read_cities(dst / "cities500.txt")
    assert stats["anchor_rows"] > 0
    # 花桥镇离昆山市（31.39,120.98）比上海近 → 归一到昆山市
    assert rows["1790701"][1] == "江苏 · 昆山市"


def test_level_town_keeps_village_names(geodata_src, tmp_path):
    dst = tmp_path / "out"
    geodata.run(geodata_src, dst, level="town", prefix="none", quiet=True)
    rows = read_cities(dst / "cities500.txt")
    assert rows["1790645"][1] == "康桥镇"
    assert rows["1609350"][1] == "曼谷"


def test_level_town_with_prefix(geodata_src, tmp_path):
    dst = tmp_path / "out"
    geodata.run(geodata_src, dst, level="town", quiet=True)
    rows = read_cities(dst / "cities500.txt")
    assert rows["1790645"][1] == "上海 · 康桥镇"


def test_level_and_prefix_stats(geodata_src, tmp_path):
    stats = geodata.run(geodata_src, tmp_path / "out", level="county", prefix="none", quiet=True)
    assert stats["level"] == "county"
    assert stats["prefix"] == "none"
    for key in ("enhance_rows", "alternate_rows", "amap_rows", "anchor_rows"):
        assert key in stats


def test_invalid_level_rejected(geodata_src, tmp_path):
    with pytest.raises(ValueError):
        geodata.run(geodata_src, tmp_path / "out", level="province", quiet=True)
    with pytest.raises(ValueError):
        geodata.run(geodata_src, tmp_path / "out", prefix="country", quiet=True)


# --------------------------------------------------------------------------
# GCJ-02 / 高德响应解析 / 缓存写入
# --------------------------------------------------------------------------
def test_wgs84_to_gcj02_reference():
    # 参考值来自 eviltransform 的公开测试向量
    assert geodata_amap.wgs84_to_gcj02(31.1774276, 121.5272106) == pytest.approx(
        (31.17530398364597, 121.531541859215), abs=1e-9
    )


@pytest.mark.parametrize(
    ("lat", "lon"),
    [(35.68, 139.69), (-33.0, -70.0), (-33.0, 151.0)],
)
def test_wgs84_to_gcj02_outside_china_returns_input(lat, lon):
    assert geodata_amap.wgs84_to_gcj02(lat, lon) == (lat, lon)


def test_parse_regeo_batch_and_single():
    batch = {
        "status": "1",
        "regeocodes": [
            {"addressComponent": {"province": "上海市", "city": [], "district": "浦东新区", "township": "康桥镇"}},
            {"addressComponent": {"province": list, "city": "苏州市", "district": "昆山市", "township": []}},
        ],
    }
    rows = geodata_amap.parse_regeo(batch)
    assert rows[0] == {"admin1": "上海市", "admin2": "", "admin3": "浦东新区", "admin4": "康桥镇"}
    assert rows[1]["admin2"] == "苏州市"
    assert rows[1]["admin3"] == "昆山市"
    assert rows[1]["admin4"] == ""

    single = {"status": "1", "regeocode": {"addressComponent": {"province": "江苏省", "city": "苏州市"}}}
    assert geodata_amap.parse_regeo(single)[0]["admin2"] == "苏州市"
    assert geodata_amap.parse_regeo({"status": "1", "regeocode": {}}) == []


def test_fetch_cache_writes_rows_and_is_incremental(tmp_path):
    out = tmp_path / "cache.csv"
    calls: list[dict] = []

    def fake_http(url, params, timeout):
        calls.append(params)
        count = len(params["location"].split("|"))
        return {
            "status": "1",
            "regeocodes": [
                {"addressComponent": {"province": "江苏省", "city": "苏州市", "district": f"区{i}", "township": "镇"}}
                for i in range(count)
            ],
        }

    candidates = [
        {"geonameid": "1", "cc": "CN", "lat": "31.15", "lon": "121.6"},
        {"geonameid": "2", "cc": "CN", "lat": "31.16", "lon": "121.61"},
    ]
    written = geodata_amap.fetch_cache(candidates, "fake-key", out, batch_size=20, quiet=True, http_get=fake_http)
    assert written == 2
    assert len(calls) == 1
    cache = geodata_names.load_amap_cache(out)
    assert cache["1"]["admin2"] == "苏州市"

    # 第二次运行：全部已缓存，不应再发请求
    written_again = geodata_amap.fetch_cache(candidates, "fake-key", out, quiet=True, http_get=fake_http)
    assert written_again == 0
    assert len(calls) == 1


def test_fetch_cache_raises_on_amap_error(tmp_path):
    def failing_http(url, params, timeout):
        return {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT"}

    with pytest.raises(RuntimeError, match="DAILY_QUERY_OVER_LIMIT"):
        geodata_amap.fetch_cache(
            [{"geonameid": "1", "cc": "CN", "lat": "31.15", "lon": "121.6"}],
            "fake-key",
            tmp_path / "cache.csv",
            quiet=True,
            http_get=failing_http,
        )


def test_read_coords_with_and_without_header(tmp_path):
    with_header = tmp_path / "with-header.csv"
    with_header.write_text("latitude,longitude\n31.15,121.6\n31.16,121.61\n", encoding="utf-8")
    assert geodata_amap.read_coords(with_header) == [(31.15, 121.6), (31.16, 121.61)]

    plain = tmp_path / "plain.csv"
    plain.write_text("31.15,121.6\nbad,row\n", encoding="utf-8")
    assert geodata_amap.read_coords(plain) == [(31.15, 121.6)]


def test_collect_candidates_maps_coords_to_nearest_row(geodata_src):
    candidates = geodata_amap.collect_candidates(geodata_src, [(31.15, 121.6), (36.09, 111.52)])
    ids = {item["geonameid"] for item in candidates}
    assert "1790645" in ids  # 康桥镇
    assert "1785603" in ids  # 临汾


def test_collect_candidates_skips_foreign(geodata_src):
    candidates = geodata_amap.collect_candidates(geodata_src, [(13.75, 100.5)])
    assert candidates == []


# --------------------------------------------------------------------------
# 离线预览（geodata-sim）
# --------------------------------------------------------------------------
def test_simulate_reports_immich_style_location(geodata_src, tmp_path):
    from immich_amap import geodata_sim

    dst = tmp_path / "out"
    geodata.run(geodata_src, dst, quiet=True)
    results = geodata_sim.simulate(dst, [(31.15, 121.6), (36.09, 111.52), (-33.0, -70.0)])

    assert results[0]["city"] == "上海市"
    assert results[0]["state"] == "上海"
    assert results[0]["country"] == "中国"
    assert results[1]["city"] == "山西 · 临汾市"

    summary = geodata_sim.summarize(results)
    assert summary["total"] == 3
    assert summary["with_city"] == 3
    assert summary["only_country"] == 0
    assert summary["village"] == 0


def test_simulate_compare_prints_diff(geodata_src, tmp_path, capsys):
    from immich_amap import geodata_sim

    city_dst = tmp_path / "city"
    town_dst = tmp_path / "town"
    geodata.run(geodata_src, city_dst, quiet=True)
    geodata.run(geodata_src, town_dst, level="town", prefix="none", quiet=True)

    coords = tmp_path / "assets.csv"
    coords.write_text("latitude,longitude\n31.15,121.6\n36.09,111.52\n", encoding="utf-8")
    exit_code = geodata_sim.main(
        ["--src", str(city_dst), "--coords", str(coords), "--compare", str(town_dst)]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "两档差异" in output
    assert "上海市" in output


def test_simulate_only_country_when_no_row_within_radius(geodata_src, tmp_path):
    from immich_amap import geodata_sim

    dst = tmp_path / "out"
    geodata.run(geodata_src, dst, quiet=True)
    results = geodata_sim.simulate(dst, [(0.0, 0.0)])
    assert results[0]["city"] == ""
    assert geodata_sim.summarize(results)["only_country"] == 1


def test_level_town_falls_back_to_chinese_anchor(geodata_src, tmp_path):
    """town 档：没有中文名的点不应把英文名写进 city，而是归一到最近中文锚点。"""
    dst = tmp_path / "out"
    geodata.run(geodata_src, dst, level="town", prefix="none", quiet=True)
    rows = read_cities(dst / "cities500.txt")
    # Pattaya 在 fixture 里没有中文别名，最近的中文锚点是曼谷
    assert rows["1614295"][1] == "曼谷"


def test_traditional_suffix_is_not_treated_as_city(geodata_src, tmp_path):
    """名字列本身是繁体「鎮」时，必须先转简再判定，否则会被误当城市锚点（历史 bug 回归）。"""
    src = tmp_path / "src-trad"
    src.mkdir()
    for name in ("countryInfo.txt", "admin1CodesASCII.txt", "admin2Codes.txt", "ne_10m_admin_0_countries.geojson"):
        (src / name).write_text((geodata_src / name).read_text(encoding="utf-8"), encoding="utf-8")
    rows = (geodata_src / "cities500.txt").read_text(encoding="utf-8").splitlines()
    # name 列（第 2 列）直接是繁体「聖馬丁將軍鎮」，无中文别名可挑；
    # 若先判 is_city 再转简，PPLA2 + 繁体「鎮」会绕过 SUB_UNIT 被当城市锚点。
    fields = city_row("1785700", "聖馬丁將軍鎮", "", 36.1, 111.6, "PPLA2", "CN", "24", 0).split("\t")
    fields[2] = "聖馬丁將軍鎮"
    rows.append("\t".join(fields))
    (src / "cities500.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")

    dst = tmp_path / "out-trad"
    geodata.run(src, dst, quiet=True)
    out = read_cities(dst / "cities500.txt")
    # 转简后以「镇」结尾 → 不是城市锚点 → 归一化到最近城市临汾
    assert out["1785700"][1] == "山西 · 临汾市"
    assert "鎮" not in out["1785700"][1]  # name 列已转简；alternate names 原列保留不动


def test_load_amap_cache_rejects_headerless_file(tmp_path):
    bogus = tmp_path / "bogus.csv"
    bogus.write_text("1790645,上海市,,浦东新区,康桥镇\n", encoding="utf-8")
    with pytest.raises(ValueError, match="geonameid"):
        geodata_names.load_amap_cache(bogus)


def test_enhance_skips_malformed_rows(geodata_src, tmp_path):
    dump = tmp_path / "broken.txt"
    dump.write_text(
        "\n".join(
            [
                "too\tfew\tcolumns",
                city_row("1790800", "Good", "好镇", 31.2, 121.2, "P", "CN", "31", 5000),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    stats = geodata.run(geodata_src, tmp_path / "out", enhance=[dump], quiet=True)
    assert stats["enhance_rows"] == 1


def test_empty_cities_does_not_crash(tmp_path):
    src = tmp_path / "src-empty"
    src.mkdir()
    for name in ("cities500.txt", "admin1CodesASCII.txt", "admin2Codes.txt", "countryInfo.txt",
                 "ne_10m_admin_0_countries.geojson"):
        (src / name).write_text("", encoding="utf-8")
    geojson = '{"type":"FeatureCollection","features":[]}'
    (src / "ne_10m_admin_0_countries.geojson").write_text(geojson, encoding="utf-8")
    stats = geodata.run(src, tmp_path / "out", quiet=True)
    assert stats["cities_total"] == 0
    assert stats["anchor_rows"] == 0


def test_run_rejects_dst_equals_src(geodata_src):
    with pytest.raises(ValueError, match="不能与 --src 相同"):
        geodata.run(geodata_src, geodata_src, quiet=True)


def test_sim_rejects_missing_support_files(tmp_path):
    from immich_amap import geodata_sim

    only_cities = tmp_path / "geo"
    only_cities.mkdir()
    (only_cities / "cities500.txt").write_text("", encoding="utf-8")
    coords = tmp_path / "coords.csv"
    coords.write_text("31.15,121.6\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        geodata_sim.main(["--src", str(only_cities), "--coords", str(coords)])


# --------------------------------------------------------------------------
# 第二遍复查发现的修复项
# --------------------------------------------------------------------------
def test_amap_province_name_is_not_used_as_city(geodata_src, tmp_path):
    """H1：只有省份名的高德缓存不能写出「山西 · 山西省」。"""
    cache = tmp_path / "province.csv"
    cache.write_text(
        "geonameid,cc,lat,lon,admin1,admin2,admin3,admin4,fetched_at\n"
        "1785603,CN,36.09,111.52,山西省,,,,\n",
        encoding="utf-8",
    )
    geodata.run(geodata_src, tmp_path / "out", amap_cache=cache, quiet=True)
    rows = read_cities(tmp_path / "out" / "cities500.txt")
    assert rows["1785603"][1] == "山西 · 临汾市"


def test_amap_placeholder_ignored(geodata_src, tmp_path):
    """H1：高德占位值「省直辖县级行政区划」不能进 city。"""
    cache = tmp_path / "placeholder.csv"
    cache.write_text(
        "geonameid,cc,lat,lon,admin1,admin2,admin3,admin4,fetched_at\n"
        "1785603,CN,36.09,111.52,山西省,省直辖县级行政区划,,\n",
        encoding="utf-8",
    )
    geodata.run(geodata_src, tmp_path / "out", amap_cache=cache, quiet=True)
    rows = read_cities(tmp_path / "out" / "cities500.txt")
    assert rows["1785603"][1] == "山西 · 临汾市"


def test_fetch_cache_skips_province_only_and_keeps_hk(tmp_path):
    out = tmp_path / "cache.csv"

    def fake_http(url, params, timeout):
        return {
            "status": "1",
            "regeocodes": [
                {"addressComponent": {"province": "湖北省", "city": [], "district": [], "township": []}},
                {"addressComponent": {"province": "香港特别行政区", "city": [], "district": [], "township": []}},
            ],
        }

    written = geodata_amap.fetch_cache(
        [
            {"geonameid": "1", "cc": "CN", "lat": "30.5", "lon": "114.3"},
            {"geonameid": "2", "cc": "HK", "lat": "22.3", "lon": "114.17"},
        ],
        "fake-key",
        out,
        quiet=True,
        http_get=fake_http,
    )
    cache = geodata_names.load_amap_cache(out)
    assert written == 1  # 只有省份的湖北行不落缓存
    assert "2" in cache and cache["2"]["admin1"] == "香港特别行政区"
    assert "1" not in cache


def test_short_and_empty_lines_are_tolerated(geodata_src, tmp_path):
    """M1：cities500 空行/单字段行不能抛 IndexError，且原样保留。"""
    src = tmp_path / "src-short"
    src.mkdir()
    for name in ("countryInfo.txt", "admin1CodesASCII.txt", "admin2Codes.txt", "ne_10m_admin_0_countries.geojson"):
        (src / name).write_text((geodata_src / name).read_text(encoding="utf-8"), encoding="utf-8")
    rows = (geodata_src / "cities500.txt").read_text(encoding="utf-8").splitlines()
    (src / "cities500.txt").write_text("\n".join(rows) + "\n\nlonely\n", encoding="utf-8")

    stats = geodata.run(src, tmp_path / "out", quiet=True)
    assert stats["cities_total"] == 11
    output = (tmp_path / "out" / "cities500.txt").read_text(encoding="utf-8").splitlines()
    assert output[-2] == "" and output[-1] == "lonely"


@pytest.mark.parametrize("separator", ["", "\t", "\n", " ·\t"])
def test_invalid_separator_rejected(geodata_src, tmp_path, separator):
    with pytest.raises(ValueError, match="separator"):
        geodata.run(geodata_src, tmp_path / "out", separator=separator, quiet=True)


def test_alternate_index_skips_short_names(tmp_path):
    path = tmp_path / "alternateNamesV2.txt"
    path.write_text(
        "\n".join(
            [
                "1\t1614295\tzh\t沪\t1\t1\t0\t0\t\t",  # preferred 但 isShortName=1
                "2\t1614295\tzh\t上海\t0\t0\t0\t0\t\t",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    index = geodata_names.build_alternate_index(path, {"1614295"})
    assert index["1614295"] == "上海"


def test_load_amap_cache_accepts_bom(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes(
        "\ufeffgeonameid,cc,lat,lon,admin1,admin2,admin3,admin4,fetched_at\n"
        "1790645,CN,31.15,121.6,上海市,,浦东新区,康桥镇,2026-11-07T00:00:00+00:00\n".encode("utf-8")
    )
    cache = geodata_names.load_amap_cache(path)
    assert cache["1790645"]["admin3"] == "浦东新区"


def test_default_conversion_ignores_optional_backend(monkeypatch):
    """M7：装了 zhconv/opencc 也不能改变默认档的繁简转换结果。"""
    monkeypatch.setattr(geodata_names, "_converter", lambda: lambda _text: "被全量转换")
    assert geodata_names.to_simplified("黃山市") == "黄山市"
    assert geodata_names.to_simplified_alias("黃山市") == "被全量转换"


def test_grid_finds_high_latitude_anchor():
    """高纬度 1 经度 ≈ 38km，旧 span 会漏掉 130km 外的锚点。"""
    grid = geodata.Grid()
    grid.add({"name": "锚点", "lat": 70.0, "lon": 0.0, "cc": "NO", "code": "PPLC", "pop": 0})
    hit = grid.nearest(70.0, 3.5, 150)  # 约 133km 正东
    assert hit is not None and hit["name"] == "锚点"


def test_load_amap_cache_empty_file_returns_empty(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert geodata_names.load_amap_cache(empty) == {}


def test_has_usable_admin_ignores_placeholders():
    assert not geodata_names.has_usable_admin(
        {"admin1": "湖北省", "admin2": "省直辖县级行政区划", "admin3": "", "admin4": ""}
    )
    assert not geodata_names.has_usable_admin({"admin1": "湖北省", "admin2": "", "admin3": "", "admin4": ""})
    assert geodata_names.has_usable_admin({"admin1": "香港特别行政区", "admin2": "", "admin3": "", "admin4": ""})
    assert geodata_names.has_usable_admin({"admin1": "", "admin2": "", "admin3": "浦东新区", "admin4": ""})


def test_http_errors_do_not_leak_api_key(monkeypatch):
    import urllib.error

    def fake_urlopen(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://restapi.amap.com/v3/geocode/regeo?key=SECRET-KEY", 403, "Forbidden", None, None
        )

    monkeypatch.setattr(geodata_amap.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError) as excinfo:
        geodata_amap._default_http_get("https://restapi.amap.com/v3/geocode/regeo", {"key": "SECRET-KEY"}, 1.0)
    assert "SECRET-KEY" not in str(excinfo.value)


def test_simulate_skips_malformed_rows(tmp_path):
    from immich_amap import geodata_sim

    src = tmp_path / "geo"
    src.mkdir()
    (src / "cities500.txt").write_text(
        "1\tBroken\tBroken\t\tbad\tbad\tP\tPPL\tCN\t\t31\t\t\t\t0\t\t\t\t\n",
        encoding="utf-8",
    )
    (src / "admin1CodesASCII.txt").write_text("CN.31\t上海\t上海\t1\n", encoding="utf-8")
    (src / "countryInfo.txt").write_text("CN\tCHN\t156\tCN\t中国\n", encoding="utf-8")
    assert geodata_sim.simulate(src, [(31.2, 121.5)])[0]["city"] == ""


def test_amap_province_direct_county_uses_district_name(geodata_src, tmp_path):
    """省直辖县级市：admin2 是占位值、admin1 是省名，应回退到 admin3 的市名。"""
    src = tmp_path / "src-hubei"
    src.mkdir()
    for name in ("countryInfo.txt", "admin2Codes.txt", "ne_10m_admin_0_countries.geojson", "cities500.txt"):
        (src / name).write_text((geodata_src / name).read_text(encoding="utf-8"), encoding="utf-8")
    (src / "admin1CodesASCII.txt").write_text(
        (geodata_src / "admin1CodesASCII.txt").read_text(encoding="utf-8") + "CN.42\tHubei\tHubei\t1795914\n",
        encoding="utf-8",
    )
    rows = (src / "cities500.txt").read_text(encoding="utf-8").splitlines()
    rows.append(city_row("1790600", "Xiantao", "", 30.36, 113.45, "PPLA3", "CN", "42", 500000))
    (src / "cities500.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    cache = tmp_path / "direct.csv"
    cache.write_text(
        "geonameid,cc,lat,lon,admin1,admin2,admin3,admin4,fetched_at\n"
        "1790600,CN,30.36,113.45,湖北省,省直辖县级行政区划,仙桃市,,\n",
        encoding="utf-8",
    )
    geodata.run(src, tmp_path / "out", amap_cache=cache, quiet=True)
    out = read_cities(tmp_path / "out" / "cities500.txt")
    assert out["1790600"][1] == "湖北 · 仙桃市"


def test_unhandled_row_falls_back_to_any_chinese_name(tmp_path):
    """150km 内没有城市锚点时，退回「任意中文名」而不是英文（瑙鲁/阿根廷回归修复）。"""
    src = tmp_path / "src-cjk"
    src.mkdir()
    (src / "countryInfo.txt").write_text(
        "# header\nCL\tCHL\t152\tCI\tChile\tSantiago\n", encoding="utf-8"
    )
    (src / "admin1CodesASCII.txt").write_text("CL.01\tAntofagasta\tAntofagasta\t1\n", encoding="utf-8")
    (src / "admin2Codes.txt").write_text("", encoding="utf-8")
    (src / "ne_10m_admin_0_countries.geojson").write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"ISO_A2":"CL","NAME_ZH":"智利"}}]}',
        encoding="utf-8",
    )
    rows = [
        city_row("1", "Rio", "", -33.0, -70.0, "PPL", "CL", "01", 500),
        city_row("2", "Cun", "某某区", -33.01, -70.01, "PPL", "CL", "01", 300),
    ]
    (src / "cities500.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")

    geodata.run(src, tmp_path / "out", quiet=True)
    out = read_cities(tmp_path / "out" / "cities500.txt")
    assert out["1"][1] == "智利 · 某某区"  # 英文行通过中文名兜底变成中文


def test_read_coords_skips_nan_inf_and_out_of_range(tmp_path):
    path = tmp_path / "coords.csv"
    path.write_text("latitude,longitude\nnan,121\ninf,122\n31.2,121.5\n91,0\n0,181\n", encoding="utf-8")
    assert geodata_amap.read_coords(path) == [(31.2, 121.5)]


def test_bad_coordinate_city_row_does_not_abort(geodata_src, tmp_path):
    src = tmp_path / "src-bad"
    src.mkdir()
    for name in ("countryInfo.txt", "admin1CodesASCII.txt", "admin2Codes.txt", "ne_10m_admin_0_countries.geojson"):
        (src / name).write_text((geodata_src / name).read_text(encoding="utf-8"), encoding="utf-8")
    rows = (geodata_src / "cities500.txt").read_text(encoding="utf-8").splitlines()
    bad = city_row("9998", "Broken", "坏行", 0, 0, "PPL", "CN", "31", 0).split("\t")
    bad[4] = "not-a-float"
    rows.append("\t".join(bad))
    (src / "cities500.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")

    stats = geodata.run(src, tmp_path / "out", quiet=True)
    assert stats["cities_total"] == 10
    output = read_cities(tmp_path / "out" / "cities500.txt")
    assert output["9998"][1] == "Broken"  # 坏坐标行原样保留（不解析名字）


def test_fetch_cache_creates_private_file(tmp_path):
    out = tmp_path / "private.csv"

    def fake_http(url, params, timeout):
        return {
            "status": "1",
            "regeocodes": [
                {"addressComponent": {"province": "上海市", "city": [], "district": "浦东新区", "township": "康桥镇"}}
            ],
        }

    geodata_amap.fetch_cache(
        [{"geonameid": "1", "cc": "CN", "lat": "31.15", "lon": "121.6"}],
        "fake-key",
        out,
        quiet=True,
        http_get=fake_http,
    )
    assert out.stat().st_mode & 0o777 == 0o600


def test_cli_reports_separator_error_without_traceback(geodata_src, capsys):
    with pytest.raises(SystemExit) as excinfo:
        geodata.main(["--src", str(geodata_src), "--dst", str(geodata_src / "out"), "--separator", "\t"])
    assert excinfo.value.code == 2


def test_amap_city_level_keeps_hk_mo_heuristic(tmp_path):
    """city 档不覆盖港澳：保留启发式的「路氹城」，避免退化成只有「澳门」。"""
    src = tmp_path / "src-mo"
    src.mkdir()
    (src / "countryInfo.txt").write_text("# header\nMO\tMAC\t446\tMO\tMacau\tMacau\n", encoding="utf-8")
    (src / "admin1CodesASCII.txt").write_text("MO.01\tMacau\tMacau\t1\n", encoding="utf-8")
    (src / "admin2Codes.txt").write_text("", encoding="utf-8")
    (src / "ne_10m_admin_0_countries.geojson").write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"ISO_A2":"MO","NAME_ZH":"中国澳门"}}]}',
        encoding="utf-8",
    )
    (src / "cities500.txt").write_text(
        city_row("1821292", "Coloane", "路氹城", 22.118, 113.552, "PPL", "MO", "", 1000) + "\n",
        encoding="utf-8",
    )
    cache = tmp_path / "mo.csv"
    cache.write_text(
        "geonameid,cc,lat,lon,admin1,admin2,admin3,admin4,fetched_at\n"
        "1821292,MO,22.118,113.552,澳门特别行政区,,圣方济各堂区,,\n",
        encoding="utf-8",
    )
    geodata.run(src, tmp_path / "out", amap_cache=cache, quiet=True)
    rows = read_cities(tmp_path / "out" / "cities500.txt")
    assert rows["1821292"][1] == "路氹城"  # 保留启发式名字，不被「圣方济各堂区」覆盖


def test_amap_city_level_uses_admin3_for_autonomous_prefecture(tmp_path):
    """自治州：city 档用 admin3 的市名（兴义市），而不是长州名。"""
    src = tmp_path / "src-gz"
    src.mkdir()
    (src / "countryInfo.txt").write_text("# header\nCN\tCHN\t156\tCN\tChina\tBeijing\n", encoding="utf-8")
    (src / "admin1CodesASCII.txt").write_text("CN.18\tGuizhou\tGuizhou\t1\n", encoding="utf-8")
    (src / "admin2Codes.txt").write_text("", encoding="utf-8")
    (src / "ne_10m_admin_0_countries.geojson").write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"ISO_A2":"CN","NAME_ZH":"中国"}}]}',
        encoding="utf-8",
    )
    (src / "cities500.txt").write_text(
        city_row("1807566", "Xingyi", "兴义,兴义市", 25.096, 104.906, "PPLA", "CN", "18", 800000) + "\n",
        encoding="utf-8",
    )
    cache = tmp_path / "gz.csv"
    cache.write_text(
        "geonameid,cc,lat,lon,admin1,admin2,admin3,admin4,fetched_at\n"
        "1807566,CN,25.096,104.906,贵州省,黔西南布依族苗族自治州,兴义市,桔山街道,\n",
        encoding="utf-8",
    )
    geodata.run(src, tmp_path / "out", amap_cache=cache, quiet=True)
    rows = read_cities(tmp_path / "out" / "cities500.txt")
    assert rows["1807566"][1] == "贵州 · 兴义市"
