"""The runs-to-viewer data contract (viewer/contract.py), on real demo logs and on broken copies."""

from __future__ import annotations

import copy

import pytest

from viewer import contract, logread, make_demo


@pytest.fixture(scope="module")
def views(tmp_path_factory):
    root = tmp_path_factory.mktemp("runs")
    mp = pytest.MonkeyPatch()
    mp.setattr(make_demo, "OUT", root)
    try:
        make_demo.write("pilot", "sonnet", 11, "stakes", "stakes", max_turns=30)
        make_demo.write("pilot", "haiku", 12, "no_stakes", "no_stakes", max_turns=30)
        make_demo.write("confirmatory", "opus", 7, "stakes", "C-TESTA", max_turns=30)
    finally:
        mp.undo()
    out = {}
    for log in sorted(root.rglob("*.jsonl.gz")):
        v = logread.episode_view(log, log.name)
        key = "blind" if v["blinded"] else ("stakes" if v["header"]["condition_code"] == "stakes" else "no_stakes")
        out[key] = v
        out[key + "_unblinded"] = logread.episode_view(log, log.name, show_blinded=True)
    return out


def test_demo_episodes_meet_the_contract(views):
    for key in ("stakes", "no_stakes", "blind", "blind_unblinded"):
        assert contract.check_episode(views[key]) == [], key


def test_not_ready_episode():
    assert contract.check_episode({"path": "x", "ready": False}) == []
    assert contract.check_episode({"path": "x", "ready": False, "turns": []})


def test_blinded_turn_with_a_new_field_fails(views):
    v = copy.deepcopy(views["blind"])
    v["turns"][3]["energy"] = 12
    probs = contract.check_episode(v)
    assert any("blind keep list" in p and "energy" in p for p in probs)


def test_any_unlisted_field_fails_when_blinded(views):
    v = copy.deepcopy(views["blind"])
    v["turns"][0]["mood_score"] = 0.4   # a field nobody has thought about yet
    assert any("mood_score" in p for p in contract.check_episode(v))


def test_blinded_end_and_diary_edits(views):
    v = copy.deepcopy(views["blind"])
    v["end"]["fainted"] = False
    v["diary_edits"] = [{"at_turn": 3}]
    probs = contract.check_episode(v)
    assert any("end line" in p for p in probs)
    assert any("diary edit" in p for p in probs)


def test_unblinded_turns_may_carry_more(views):
    v = views["stakes"]
    assert "energy" in v["turns"][0]
    assert contract.check_episode(v) == []


def test_teleport_is_caught(views):
    v = copy.deepcopy(views["stakes"])
    r, c = v["turns"][5]["position"]
    v["turns"][5]["position"] = [(r + 3) % 11, c]
    assert any("after moving" in p for p in contract.check_episode(v))


def test_skipped_turn_is_caught(views):
    v = copy.deepcopy(views["stakes"])
    del v["turns"][4]
    assert any("count up by one" in p or "after moving" in p for p in contract.check_episode(v))


def test_bad_map_region_and_move(views):
    v = copy.deepcopy(views["stakes"])
    v["turns"][2]["map"][0] = "X" * 11
    v["turns"][2]["chosen_region"] = 9
    v["turns"][2]["move"] = "fly"
    probs = contract.check_episode(v)
    assert any("map row 0" in p for p in probs)
    assert any("chosen_region" in p for p in probs)
    assert any("'fly'" in p for p in probs)


def test_missing_keys(views):
    v = copy.deepcopy(views["stakes"])
    del v["turns"][1]["shown_region"]
    del v["map_ok"]
    probs = contract.check_episode(v)
    assert probs == ["missing top-level key 'map_ok'"]
    v["map_ok"] = True
    assert any("missing ['shown_region']" in p for p in contract.check_episode(v))


def test_header_shape(views):
    v = copy.deepcopy(views["stakes"])
    v["header"]["api_key_hint"] = "x"
    assert any("header must carry exactly" in p for p in contract.check_episode(v))


def test_running_flags(views):
    v = copy.deepcopy(views["stakes"])
    v["running"] = True
    assert any("running episode" in p for p in contract.check_episode(v))
