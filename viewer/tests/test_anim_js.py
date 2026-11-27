"""Runs the browser animation code (static/anim.js) under node.

Two layers: the node unit tests in tests/js, and an end-to-end pass that takes a
scripted demo episode through logread, the real frames.js and anim.js, and checks
the plans against the log. Skipped where node isn't installed; the rest of the
viewer tests don't need it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from viewer import logread, make_demo

HERE = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node isn't installed")

STEP = {"north": (-1, 0), "south": (1, 0), "east": (0, 1), "west": (0, -1)}


def test_node_unit_tests_pass():
    r = subprocess.run([NODE, "--test", str(HERE / "js" / "anim.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]


@pytest.fixture(scope="module")
def demo_view(tmp_path_factory):
    root = tmp_path_factory.mktemp("runs")
    mp = pytest.MonkeyPatch()
    mp.setattr(make_demo, "OUT", root)
    try:
        make_demo.write("pilot", "sonnet", 11, "stakes", "stakes", max_turns=40)
    finally:
        mp.undo()
    log = next((root / "pilot").rglob("*.jsonl.gz"))
    return logread.episode_view(log, "demo.jsonl.gz")


def _plan(view, tmp_path, turn_ms=950):
    f = tmp_path / "ep.json"
    f.write_text(json.dumps(view), encoding="utf-8")
    r = subprocess.run([NODE, str(HERE / "js" / "plan_episode.mjs"), str(f), str(turn_ms)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


def test_demo_episode_plans_match_the_log(demo_view, tmp_path):
    plans = _plan(demo_view, tmp_path)
    turns = demo_view["turns"]
    assert len(plans) == len(turns) + (1 if demo_view["end"] else 0)
    for p in plans:
        moved = p["from"] is not None and p["from"] != p["pos"]
        walks = [c for c in p["clips"] if c.startswith("walk_")]
        assert len(walks) == (1 if moved else 0), p
        if moved:
            dr, dc = p["pos"][0] - p["from"][0], p["pos"][1] - p["from"][1]
            want = {v: k for k, v in STEP.items()}[(dr, dc)]
            assert walks[0] == f"walk_{want}" and p["facing"] == want
        # every event with a clip got its clip
        for ev, clip in (("eat", "eat"), ("ouch", "ouch"), ("checkin", "think"), ("faint", "faint")):
            assert (ev in p["events"]) == (clip in p["clips"]), p
        # by the end of the turn the critter stands on its tile, feet down
        assert p["end"]["pos"] == p["pos"] and p["end"]["hop"] == 0
        assert p["fitted"] <= 950 + 1e-6


def test_demo_episode_has_eating_and_walking(demo_view, tmp_path):
    plans = _plan(demo_view, tmp_path)
    clips = [c for p in plans for c in p["clips"]]
    assert any(c.startswith("walk_") for c in clips)
    assert "eat" in clips


def test_fast_playback_still_fits(demo_view, tmp_path):
    plans = _plan(demo_view, tmp_path, turn_ms=120)
    assert all(p["fitted"] <= 120 + 1e-6 for p in plans)


def test_blinded_episode_plans_without_secrets(tmp_path_factory, tmp_path):
    root = tmp_path_factory.mktemp("blind")
    mp = pytest.MonkeyPatch()
    mp.setattr(make_demo, "OUT", root)
    try:
        make_demo.write("confirmatory", "opus", 7, "stakes", "C-TESTA", max_turns=30)
    finally:
        mp.undo()
    view = logread.episode_view(next(root.rglob("*.jsonl.gz")), "b.jsonl.gz")
    assert view["blinded"]
    plans = _plan(view, tmp_path)
    # moods in blinded mode can't come from meters, so no worried idles
    assert all(p["rest"] != "idle_worried" for p in plans)
