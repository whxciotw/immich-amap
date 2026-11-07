"""中文地名库改写测试（合成 fixture，不依赖真实 GeoNames 数据）。"""

from __future__ import annotations

import json
import pathlib

import pytest

from immich_amap import geodata

COUNTRY_HEADER = (
    "# GeoNames countryInfo.txt\n"
    "# ISO\tISO3\tISO-Numeric\tfips\tCountry\tCapital\n"
)


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
) -> str:
    fields = [
        gid, name, name, alternates, lat, lon, "P", fcode, cc, "",
        admin1, "", "", "", population, "", "", "Asia/Shanghai", "2026-01-01",
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
                # 城市：直辖市、地级市、境外城市、港澳台
                city_row("1796236", "Shanghai", "上海,上海市", 31.22222, 121.45806, "PPLA", "CN", "31", 24256800),
                city_row("1785603", "Linfen", "临汾,临汾市", 36.08889, 111.51889, "PPL", "CN", "24", 500000),
                city_row("1609350", "Bangkok", "曼谷", 13.75, 100.5, "PPLC", "TH", "40", 5104476),
                city_row("1819729", "Hong Kong", "香港", 22.28, 114.17, "PPLC", "HK", "", 7482500),
                city_row("1668341", "Taipei", "台北,台北市", 25.05, 121.5, "PPLC", "TW", "", 7871900),
                city_row("1821274", "Macau", "澳门", 22.2, 113.54, "PPLC", "MO", "", 600000),
                # 非城市：应被归一化到最近城市
                city_row("1790645", "Kangqiao", "康桥镇", 31.15, 121.6, "PPL", "CN", "31", 100000),
                city_row("1611111", "Bang Kapi", "邦卡皮", 13.76, 100.6, "PPL", "TH", "40", 1000),
                # 非城市且 150km 内没有城市：保持原样
                city_row("9999999", "Somewhere", "某某", -33.0, -70.0, "PPL", "CL", "", 100),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return src


@pytest.fixture()
def geodata_out(geodata_src: pathlib.Path, tmp_path: pathlib.Path) -> pathlib.Path:
    dst = tmp_path / "out"
    geodata.run(geodata_src, dst, quiet=True)
    return dst


def read_cities(path: pathlib.Path) -> dict[str, list[str]]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        rows[fields[0]] = fields
    return rows


def test_country_and_province_names_are_chinese(geodata_out: pathlib.Path):
    country = {}
    for line in (geodata_out / "countryInfo.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        fields = line.split("\t")
        country[fields[0]] = fields[4]
    assert country["CN"] == "中国"
    assert country["TH"] == "泰国"

    admin1 = {}
    for line in (geodata_out / "admin1CodesASCII.txt").read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        admin1[fields[0]] = fields[1]
    assert admin1["CN.31"] == "上海"
    assert admin1["CN.24"] == "山西"
    assert admin1["HK.HC"] == "香港"


def test_city_display_names(geodata_out: pathlib.Path):
    rows = read_cities(geodata_out / "cities500.txt")
    assert rows["1796236"][1] == "上海市"
    assert rows["1785603"][1] == "山西 · 临汾市"
    assert rows["1609350"][1] == "泰国 · 曼谷"
    assert rows["1819729"][1] == "香港"
    assert rows["1668341"][1] == "台湾 · 台北市"
    assert rows["1821274"][1] == "澳门"


def test_non_city_rows_are_normalized_to_nearest_city(geodata_out: pathlib.Path):
    rows = read_cities(geodata_out / "cities500.txt")
    assert rows["1790645"][1] == "上海市"   # 康桥镇 → 上海市
    assert rows["1611111"][1] == "泰国 · 曼谷"  # 邦卡皮 → 曼谷
    assert rows["9999999"][1] == "某某"  # 附近无城市，保持原样


def test_no_city_level_keeps_village_names(geodata_src: pathlib.Path, tmp_path: pathlib.Path):
    dst = tmp_path / "out-no-city"
    stats = geodata.run(geodata_src, dst, city_level=False, quiet=True)
    rows = read_cities(dst / "cities500.txt")

    assert stats["rewritten_rows"] == 0
    assert rows["1790645"][1] == "康桥镇"
    assert rows["1611111"][1] == "邦卡皮"


def test_geodata_date_and_unchanged_files(geodata_out: pathlib.Path):
    assert (geodata_out / "geodata-date.txt").read_text(encoding="utf-8").strip()
    assert (geodata_out / "admin2Codes.txt").read_text(encoding="utf-8").startswith("CN.31.01")
    assert (geodata_out / "ne_10m_admin_0_countries.geojson").is_file()


def test_stats(geodata_out: pathlib.Path, geodata_src: pathlib.Path, tmp_path: pathlib.Path):
    stats = geodata.run(geodata_src, tmp_path / "out-again", quiet=True)
    assert stats["country_renamed"] == 6
    assert stats["admin1_renamed"] == 3
    assert stats["cities_total"] == 9
    assert stats["city_rows"] == 6
    assert stats["rewritten_rows"] == 2
    assert stats["display_with_separator"] == 4  # 临汾/曼谷/台北 3 个城市行 + 1 个归一化后的邦卡皮


# --------------------------------------------------------------------------
# 纯函数
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("traditional", "simplified"),
    [("黃山市", "黄山市"), ("長治市", "长治市"), ("芭達亞", "芭达亚"), ("上海", "上海")],
)
def test_to_simplified(traditional, simplified):
    assert geodata.to_simplified(traditional) == simplified


def test_pick_cjk_prefers_city_suffix():
    assert geodata.pick_cjk(["上海", "上海市"]) == "上海市"


def test_pick_cjk_returns_none_without_chinese():
    assert geodata.pick_cjk(["Shanghai", "Shang-hai"]) is None


def test_pick_cjk_skips_country_names():
    assert geodata.pick_cjk(["中国", "北京"]) == "北京"


def make_item(name, cc, code, population, lat=0.0, lon=0.0):
    return {"name": name, "cc": cc, "code": code, "pop": population, "lat": lat, "lon": lon}


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (make_item("上海市", "CN", "PPLA", 0), True),
        (make_item("临汾市", "CN", "PPL", 500000), True),
        (make_item("康桥镇", "CN", "PPL", 100000), False),
        (make_item("浦东新区", "CN", "PPLA4", 5000000), False),
        (make_item("曼谷", "TH", "PPLC", 0), True),
        (make_item("Somewhere", "CL", "PPLC", 0), False),  # 没有中文名
    ],
)
def test_is_city(item, expected):
    assert geodata.is_city(item) is expected


def test_grid_nearest_respects_accept_and_radius():
    grid = geodata.Grid()
    grid.add(make_item("上海市", "CN", "PPLA", 0, lat=31.22, lon=121.46))
    grid.add(make_item("北京市", "CN", "PPLA", 0, lat=39.9, lon=116.4))

    assert grid.nearest(31.15, 121.6, 150)["name"] == "上海市"
    assert grid.nearest(31.15, 121.6, 150, lambda item: item["name"] == "北京市") is None
    assert grid.nearest(-33.0, -70.0, 150) is None
    assert len(grid) == 2


def test_display_name_for_direct_controlled_municipality():
    name = geodata.display_name(
        "CN",
        "31",
        "上海市",
        country_zh={"CN": "中国"},
        country_en={"CN": "China"},
        admin1_map={"CN.31": "上海"},
    )
    assert name == "上海市"


def test_display_name_for_foreign_uses_country_prefix():
    name = geodata.display_name(
        "TH",
        "40",
        "曼谷",
        country_zh={"TH": "泰国"},
        country_en={"TH": "Thailand"},
        admin1_map={},
    )
    assert name == "泰国 · 曼谷"
