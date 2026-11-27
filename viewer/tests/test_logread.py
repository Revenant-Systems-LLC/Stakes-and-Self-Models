"""Viewer tests. They play short scripted-critter episodes, so no API calls and no credit."""

from __future__ import annotations

import gzip
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from viewer import logread, make_demo, server

SECRET_KEYS = ("energy", "health", "points", "fainted", "diary", "raw_reply", "checkin_answer",
               "checkin_yes", "edit", "wrote", "answer_field", "input_tokens", "output_tokens", "cost_usd", "calls",
               "stray_answer", "reply_notes", "checkin_question")


@pytest.fixture(scope="module")
def runs(tmp_path_factory, monkeypatch_module):
    root = tmp_path_factory.mktemp("runs")
    monkeypatch_module.setattr(make_demo, "OUT", root)
    make_demo.write("pilot", "sonnet", 11, "stakes", "stakes", max_turns=30)
    make_demo.write("confirmatory", "opus", 7, "stakes", "C-TESTA", max_turns=30)
    return root


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def _log(runs: Path, phase: str) -> Path:
    return next((runs / phase).rglob("*.jsonl.gz"))


def test_replayed_map_matches_logged_positions(runs):
    p = _log(runs, "pilot")
    header, turns, end = logread.read_partial(p)
    maps, ok = logread.replay_maps(header, turns)
    assert ok and end is not None
    assert len(maps) == len(turns)
    assert maps[0] == header["start_map"]


def test_demo_checkin_answers_land_in_the_answer_field(runs):
    _, turns, _ = logread.read_partial(_log(runs, "pilot"))
    answers = [t["checkin_answer"] for t in turns if t.get("checkin")]
    assert answers and all(answers)  # the scripted critter always answers


def test_pilot_log_shown_in_full(runs):
    p = _log(runs, "pilot")
    v = logread.episode_view(p, "x.jsonl.gz")
    assert not v["blinded"]
    assert "energy" in v["turns"][0] and "diary" in v["turns"][0]
    assert all("calls" not in t for t in v["turns"])


def test_blinded_log_stripped_on_server(runs):
    p = _log(runs, "confirmatory")
    v = logread.episode_view(p, "x.jsonl.gz")
    assert v["blinded"] and v["diary_edits"] == []
    text = json.dumps(v)
    for t in v["turns"]:
        assert set(t) <= set(logread.BLIND_TURN_KEEP) | {"map"}
    for k in SECRET_KEYS:
        assert f'"{k}"' not in text, k
    assert set(v["end"]) <= set(logread.BLIND_END_KEEP)


def test_label_alone_triggers_blinding(runs):
    p = _log(runs, "confirmatory")
    v = logread.episode_view(p, "x.jsonl.gz", blinded_phases=())
    assert v["blinded"]  # coded label, even with no blinded phases configured


def test_show_blinded_lifts_stripping(runs):
    p = _log(runs, "confirmatory")
    v = logread.episode_view(p, "x.jsonl.gz", show_blinded=True)
    assert not v["blinded"] and "energy" in v["turns"][0]


def test_partial_read_of_a_log_mid_write(runs, tmp_path):
    full = _log(runs, "pilot")
    header, turns, end = logread.read_partial(full)
    lines = [json.dumps(header)] + [json.dumps(t) for t in turns[:12]]
    raw = gzip.compress(("\n".join(lines) + "\n" + json.dumps(turns[12])[:40]).encode())
    cut = tmp_path / "running.jsonl.gz"
    cut.write_bytes(raw[:-8])  # drop the gzip trailer, like a file still being written
    h, t, e = logread.read_partial(cut)
    assert h is not None and e is None
    assert 10 <= len(t) <= 12
    v = logread.episode_view(cut, "running.jsonl.gz")
    assert v["running"] and v["map_ok"]


def test_server_refuses_paths_outside_runs(runs):
    server.Handler.runs = runs
    server.Handler.opts = {"blinded_phases": ("confirmatory",), "show_blinded": False}
    server.Handler.caps = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        eps = json.load(urllib.request.urlopen(base + "/api/episodes"))["episodes"]
        assert len(eps) == 2
        for bad in ("/api/episode?path=../../runner/config.json", "/api/episode?path=../x.jsonl.gz", "/../server.py"):
            with pytest.raises(urllib.error.HTTPError) as ei:
                urllib.request.urlopen(base + bad)
            assert ei.value.code == 404
        ok = json.load(urllib.request.urlopen(base + "/api/episode?path=" + eps[0]["path"]))
        assert ok["ready"]
    finally:
        srv.shutdown()
