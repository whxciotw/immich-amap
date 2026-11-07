"""CLI 与产物测试（全部写入 tmp_path，不碰仓库 dist/）。"""

from __future__ import annotations

import argparse
import json
import pathlib

import pytest

from immich_amap import build, cli, selftest, static


def test_tile_xy_known_points():
    assert selftest.tile_xy(0.0, 0.0, 0) == (0, 0)
    assert selftest.tile_xy(0.0, 0.0, 1) == (1, 1)
    # 北京天安门（116.3912, 39.9062）在 z16 的瓦片编号
    assert selftest.tile_xy(116.3912, 39.9062, 16) == (53956, 24832)


def test_parse_center():
    assert static.parse_center("121.4737,31.2304") == (121.4737, 31.2304)
    with pytest.raises(argparse.ArgumentTypeError):
        static.parse_center("121.6")
    with pytest.raises(argparse.ArgumentTypeError):
        static.parse_center("200,31")


def test_build_urls_writes_styles_and_manifest(tmp_path: pathlib.Path):
    assert build.main(["--tile-base", "http://192.0.2.10:9002", "--out", str(tmp_path)]) == 0

    for name in ("amap-light", "amap-dark", "amap-sat", "amap-fixed-light", "amap-fixed-dark", "amap-fixed-sat"):
        assert (tmp_path / f"{name}.json").is_file()

    urls_file = tmp_path / "urls.txt"
    styles = selftest.load_styles(urls_file)
    assert len(styles) == 6
    assert styles["amap-fixed-light"]["sources"]["amap"]["tiles"][0].startswith("http://192.0.2.10:9002/")


def test_build_urls_percent_and_emit_json(tmp_path: pathlib.Path):
    assert build.main(
        ["--tile-base", "http://h:9002", "--out", str(tmp_path), "--percent", "--emit-json"]
    ) == 0
    assert (tmp_path / "amap-light.json").is_file()
    assert not (tmp_path / "urls.txt").exists()


def test_build_urls_compact(tmp_path: pathlib.Path):
    assert build.main(["--tile-base", "http://h:9002", "--out", str(tmp_path), "--compact"]) == 0
    assert (tmp_path / "compact-light.json").is_file()
    assert (tmp_path / "compact-dark.json").is_file()
    compact = selftest.load_styles(tmp_path / "urls-compact.txt")
    assert set(compact) == {"compact-light", "compact-dark"}
    assert len(compact["compact-light"]["sources"]["amap"]["tiles"]) == 1


def test_static_writes_three_styles_with_center(tmp_path: pathlib.Path):
    assert static.main(
        [
            "--tile-base", "http://192.0.2.10:9002",
            "--center", "121.4737,31.2304",
            "--zoom", "15",
            "--out", str(tmp_path),
            "--public-base", "http://192.0.2.10:9003",
        ]
    ) == 0

    for filename in static.STYLE_FILES:
        style = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
        assert style["center"] == [121.4737, 31.2304]
        assert style["zoom"] == 15.0
        assert all(
            "/proxy/gcj2wgs/" in tile for source in style["sources"].values() for tile in source["tiles"]
        )

    manifest = (tmp_path / "urls.txt").read_text(encoding="utf-8")
    assert "http://192.0.2.10:9003/style-light.json" in manifest


def test_cli_dispatches_subcommand(tmp_path: pathlib.Path, capsys):
    assert cli.main(["urls", "--tile-base", "http://h:9002", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "urls.txt").is_file()


def test_cli_without_command_prints_help(capsys):
    assert cli.main([]) == 0
    assert "immich-amap" in capsys.readouterr().out
