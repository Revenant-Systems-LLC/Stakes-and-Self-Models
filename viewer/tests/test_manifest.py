"""The sprite manifest checker: the default manifest passes, and broken ones say why."""

from __future__ import annotations

import copy
import json
import re
import struct
import zlib
from pathlib import Path

import pytest

from viewer import manifest as mf


def _png(path: Path, w: int, h: int):
    """A tiny valid PNG of w x h, transparent."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x00" * (w * 4) for _ in range(h))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def default():
    return mf.load()


def _sheets_manifest(tmp_path: Path) -> dict:
    """A 'sheets' manifest with every clip on one 4x4 sheet of 20x20 cells."""
    _png(tmp_path / "critter.png", 80, 80)
    m = mf.load()
    m["source"] = "sheets"
    m["sheets"] = {"critter": {"image": "critter.png", "provenance": "drawn by the test suite as a blank stand-in"}}
    for i, (name, c) in enumerate(m["clips"].items()):
        if "mirror" in c:
            continue
        m["clips"][name] = {"sheet": "critter", "frames": [[i % 4, (i // 4) % 4], [(i + 1) % 4, (i // 4) % 4]],
                            "ms": c["ms"], "loop": c["loop"]}
    for i, (name, c) in enumerate(m["emotes"].items()):
        m["emotes"][name] = {"sheet": "critter", "frames": [[i % 4, 3]], "ms": 200, "loop": True}
    return m


def test_default_manifest_is_good(default):
    assert mf.check(default) == []


def test_cli_reports_ok(capsys):
    assert mf.main([str(mf.DEFAULT_PATH)]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_fails_on_bad_file(tmp_path, capsys):
    p = tmp_path / "m.json"
    p.write_text("{not json", encoding="utf-8")
    assert mf.main([str(p)]) == 1


def test_lists_match_anim_js():
    js = mf.ANIM_JS.read_text(encoding="utf-8")

    def arr(name):
        body = re.search(rf"export const {name} = \[(.*?)\];", js, re.S).group(1)
        return tuple(re.findall(r'"([a-z_]+)"', body))

    assert arr("CLIPS") == mf.REQUIRED_CLIPS
    assert arr("ONE_SHOT") == mf.ONE_SHOT
    assert arr("EMOTES") == mf.REQUIRED_EMOTES


def test_missing_clip_and_unknown_clip(default):
    m = copy.deepcopy(default)
    del m["clips"]["eat"]
    m["clips"]["eatt"] = {"frames": 1, "ms": 100, "loop": False}
    probs = mf.check(m)
    assert any("'eat' is missing" in p for p in probs)
    assert any("'eatt' isn't one the viewer uses" in p for p in probs)


def test_loop_rules(default):
    m = copy.deepcopy(default)
    m["clips"]["eat"]["loop"] = True
    m["clips"]["idle"]["loop"] = False
    probs = mf.check(m)
    assert any("'eat': plays once" in p for p in probs)
    assert any("'idle': repeats" in p for p in probs)


def test_timing_rules(default):
    m = copy.deepcopy(default)
    m["clips"]["idle"]["ms"] = 0
    m["clips"]["eat"]["ms"] = [100]          # two frames, one time
    m["clips"]["ouch"]["ms"] = "fast"
    probs = mf.check(m)
    assert any("'idle': ms 0 is out of range" in p for p in probs)
    assert any("'eat': ms has 1 entries for 2 frames" in p for p in probs)
    assert any("'ouch': ms must be" in p for p in probs)


def test_mirror_rules(default):
    m = copy.deepcopy(default)
    m["clips"]["walk_west"] = {"mirror": "walk_sideways"}
    assert any("mirrors 'walk_sideways'" in p for p in mf.check(m))
    m["clips"]["walk_west"] = {"mirror": "walk_east"}
    m["clips"]["walk_east"] = {"mirror": "walk_west"}
    assert any("itself a mirror" in p for p in mf.check(m))


def test_anchor_must_sit_in_the_cell(default):
    m = copy.deepcopy(default)
    m["anchor"] = [25, 5]
    assert any("outside the 20x20 cell" in p for p in mf.check(m))


def test_good_sheets_manifest(tmp_path):
    m = _sheets_manifest(tmp_path)
    assert mf.check(m, tmp_path) == []


def test_sheet_needs_provenance(tmp_path):
    m = _sheets_manifest(tmp_path)
    m["sheets"]["critter"]["provenance"] = ""
    assert any("provenance" in p for p in mf.check(m, tmp_path))


def test_sheet_image_must_exist_and_fit(tmp_path):
    m = _sheets_manifest(tmp_path)
    m["clips"]["idle"]["frames"] = [[4, 0]]
    m["clips"]["idle"]["ms"] = 100
    assert any("runs past the edge" in p for p in mf.check(m, tmp_path))
    m = _sheets_manifest(tmp_path)
    (tmp_path / "critter.png").unlink()
    assert any("isn't in" in p for p in mf.check(m, tmp_path))


def test_sheet_size_must_be_whole_cells(tmp_path):
    m = _sheets_manifest(tmp_path)
    _png(tmp_path / "critter.png", 85, 80)
    assert any("not a whole number" in p for p in mf.check(m, tmp_path))


@pytest.mark.parametrize("bad", ["../secret.png", "/etc/x.png", "C:/x.png", "art\\x.png", "x.gif", ""])
def test_image_paths_stay_in_the_art_folder(tmp_path, bad):
    m = _sheets_manifest(tmp_path)
    m["sheets"]["critter"]["image"] = bad
    assert any("image" in p for p in mf.check(m, tmp_path))


def test_png_size_reader(tmp_path):
    _png(tmp_path / "a.png", 40, 60)
    assert mf.png_size(tmp_path / "a.png") == (40, 60)
    (tmp_path / "b.png").write_bytes(b"not a png at all, sorry")
    assert mf.png_size(tmp_path / "b.png") is None


def test_clip_ms(default):
    assert mf.clip_ms(default, "eat") == 560
    assert mf.clip_ms(default, "walk_west") == mf.clip_ms(default, "walk_east")
    assert mf.clip_ms(default, "dots", "emotes") == 1200


def test_manifest_is_plain_json_on_disk():
    # the browser loads it with fetch(), so it must parse as strict JSON
    json.loads(mf.DEFAULT_PATH.read_text(encoding="utf-8"))
