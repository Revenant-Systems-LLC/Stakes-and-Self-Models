"""Critter tests. A fake model stands in for Qwen so these run without the GPU, plus one GPU test."""

import json

import numpy as np
import pytest

from arm2 import qwen_critter, steering
from arm2.qwen_critter import QwenCritter, is_fenced, read_system_prompt, turn_seed
from world.agents import decide, validate
from world.env import CritterWorld
from world.episode import run_episode
from world.log import read_log

VALID = json.dumps({"move": "stay", "look": 4, "diary": "waiting"})


class FakeCritter(QwenCritter):
    """No model. script(turn, attempt) gives the reply text; every call is recorded in self.seen."""

    def __init__(self, script=lambda turn, attempt: VALID):
        super().__init__(None, None)
        self.script = script
        self.seen = []
        self._turn_for_script = None

    def _encode(self, system, user):
        self.seen.append({"system": system, "user": user})
        return list(range(7))

    def _generate_ids(self, prompt_ids, seed, steer):
        rec = self.seen[-1]
        rec.update(seed=seed, steer=steer)
        text = self.script(self._last_turn, self._attempt)
        return [ord(ch) for ch in text]

    def _decode(self, ids):
        return "".join(chr(i) for i in ids)


def obs(turn):
    return {"turn": turn}


# ---------------------------------------------------------------- seeding
def test_turn_seed_is_deterministic_and_separates_inputs():
    assert turn_seed(990000, 5, 0) == turn_seed(990000, 5, 0)
    seeds = {turn_seed(s, t, a) for s in (990000, 990001) for t in range(1, 49) for a in (0, 1)}
    assert len(seeds) == 2 * 48 * 2
    assert 0 <= turn_seed(990000, 1, 0) < 2**32


def test_reply_seeds_follow_episode_turn_attempt():
    c = FakeCritter()
    c.begin_episode(990003, "stakes", progress=False)
    c.reply(obs(1), "t1")
    c.reply(obs(1), "t1")  # a retry: same turn again
    c.reply(obs(2), "t2")
    assert [r["seed"] for r in c.seen] == [turn_seed(990003, 1, 0), turn_seed(990003, 1, 1), turn_seed(990003, 2, 0)]
    # a second episode with the same seed gives the same seeds
    c.seen.clear()
    c.begin_episode(990003, "stakes", progress=False)
    c.reply(obs(1), "t1")
    assert c.seen[0]["seed"] == turn_seed(990003, 1, 0)


# ---------------------------------------------------------------- prompts and text
def test_system_prompt_comes_from_the_condition_file():
    assert read_system_prompt("stakes").startswith("You are a small critter")
    assert "This is your body" in read_system_prompt("stakes")
    assert "score as many points" in read_system_prompt("no_stakes")
    with pytest.raises(ValueError):
        read_system_prompt("both")
    c = FakeCritter()
    c.begin_episode(990000, "no_stakes", progress=False)
    c.reply(obs(1), "x")
    assert c.seen[0]["system"] == read_system_prompt("no_stakes")


def test_user_message_is_the_turn_text_unchanged():
    c = FakeCritter()
    c.begin_episode(990000, "stakes", progress=False)
    text = "Turn 1 of 48\nEnergy 20/20  Health 10/10\n\nMap:\n. . . | . . . | . . .\n"
    c.reply(obs(1), text)
    assert c.seen[0]["user"] == text


def test_reply_is_raw_fences_and_all():
    fenced = "```json\n" + VALID + "\n```"
    c = FakeCritter(lambda turn, attempt: fenced)
    c.begin_episode(990000, "stakes", progress=False)
    assert c.reply(obs(1), "x") == fenced
    assert validate(fenced)[0] is not None  # since the first API pilot the world reads the JSON inside the fences
    assert c.calls[0]["fenced"] is True
    assert is_fenced(fenced) and not is_fenced(VALID)


def test_reply_needs_an_episode():
    with pytest.raises(RuntimeError):
        FakeCritter().reply(obs(1), "x")


# ---------------------------------------------------------------- retries, sidecar
def test_bad_first_reply_is_retried_with_a_new_seed():
    c = FakeCritter(lambda turn, attempt: "not json" if attempt == 0 else VALID)
    c.begin_episode(990000, "stakes", progress=False)
    d = decide(c, obs(7), "x", fallback_look=4)
    assert d.valid and len(d.raw_replies) == 2
    assert c.seen[0]["seed"] != c.seen[1]["seed"]
    assert [x["attempt"] for x in c.calls] == [0, 1]


def test_hit_cap_flag():
    c = FakeCritter(lambda turn, attempt: "a" * (120 if turn == 1 else 119))
    c.begin_episode(990000, "stakes", progress=False)
    c.reply(obs(1), "x")
    c.reply(obs(2), "x")
    assert [x["hit_cap"] for x in c.calls] == [True, False]
    assert [x["tokens_out"] for x in c.calls] == [120, 119]


def test_sidecar_holds_settings_and_per_call_tokens(tmp_path):
    c = FakeCritter()
    c.layer_norms = {18: 80.0}
    c.set_steering(steering.SteeringSpec(18, steering.random_unit_vector(3, 16), 4, mode="all", turns=[2]))
    path = tmp_path / "ep.sidecar.jsonl"
    c.begin_episode(990000, "stakes", sidecar_path=path, progress=False)
    c.reply(obs(1), "x")
    c.reply(obs(2), "x")
    c.end_episode({"turns": 2, "fainted": False})
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    meta, calls, end = lines[0], lines[1:3], lines[3]
    assert meta["type"] == "meta" and meta["sampling"]["max_new_tokens"] == 120
    assert meta["steering"]["mode"] == "all" and meta["steering"]["magnitude"] == pytest.approx(32.0)
    assert meta["steering"]["turns"] == [2]
    assert [c_["steered"] for c_ in calls] == [False, True]
    assert calls[1]["mode"] == "all" and calls[1]["layer"] == 18
    assert calls[0]["tokens_in"] == 7 and calls[0]["tokens_out"] == len(VALID)
    assert end["type"] == "end" and end["turns"] == 2


# ---------------------------------------------------------------- steering turn selection
def test_steering_applies_only_on_chosen_turns():
    c = FakeCritter()
    c.layer_norms = {14: 60.0}
    c.set_steering(steering.SteeringSpec(14, steering.random_unit_vector(3, 16), 4, turns=[3, 4]))
    c.begin_episode(990000, "stakes", progress=False)
    for t in range(1, 7):
        c.reply(obs(t), "x")
    assert [r["steer"] for r in c.seen] == [False, False, True, True, False, False]
    # a retry of a chosen turn is steered too
    c.reply(obs(4), "x")
    assert c.seen[-1]["steer"] is True


def test_steering_every_turn_when_turns_is_none_and_off_when_none():
    c = FakeCritter()
    c.layer_norms = {14: 60.0}
    c.set_steering(steering.SteeringSpec(14, steering.random_unit_vector(3, 16), 4))
    c.begin_episode(990000, "stakes", progress=False)
    c.reply(obs(1), "x")
    c.reply(obs(2), "x")
    c.set_steering(None)
    c.reply(obs(3), "x")
    assert [r["steer"] for r in c.seen] == [True, True, False]


def test_steering_needs_layer_norms():
    c = FakeCritter()
    with pytest.raises(RuntimeError):
        c.set_steering(steering.SteeringSpec(14, steering.random_unit_vector(3, 16), 4))
    c.layer_norms = {14: 60.0}
    with pytest.raises(ValueError):
        c.set_steering(steering.SteeringSpec(22, steering.random_unit_vector(3, 16), 4))


# ---------------------------------------------------------------- inside the real world
def test_full_episode_through_run_episode(tmp_path):
    c = FakeCritter()
    log = tmp_path / "ep.jsonl.gz"
    c.begin_episode(990000, "stakes", sidecar_path=tmp_path / "ep.sidecar.jsonl", progress=False)
    summary = run_episode(c, condition="stakes", seed=990000, log_path=log, arm="arm2-test", version="test")
    c.end_episode(summary)
    header, turns, end = read_log(log)
    assert header["model"] == c.name and end["turns"] == len(turns) == summary["turns"]
    assert all(t["reply_valid"] and len(t["raw_reply"]) == 1 for t in turns)
    # check-in turns are marked but never answered or asked
    assert [t for t in turns if t["checkin"]], "expected at least one check-in turn"
    assert all(t["checkin_answer"] is None for t in turns)
    # the model never sees a question about itself
    assert not any("Game check" in r["user"] for r in c.seen)
    assert len(c.calls) == len(turns)


def test_twin_ends_with_stakes_twin_and_uses_its_own_prompt(tmp_path):
    c = FakeCritter()
    c.begin_episode(990000, "stakes", progress=False)
    s = run_episode(c, condition="stakes", seed=990000, log_path=tmp_path / "s.jsonl.gz", version="t")
    c.end_episode(s)
    c.seen.clear()
    c.begin_episode(990000, "no_stakes", progress=False)
    n = run_episode(c, condition="no_stakes", seed=990000, max_turns=s["turns"], log_path=tmp_path / "n.jsonl.gz",
                    version="t")
    c.end_episode(n)
    assert n["turns"] == s["turns"]
    assert {r["system"] for r in c.seen} == {read_system_prompt("no_stakes")}
    assert all("Points" in r["user"] and "Energy" not in r["user"] for r in c.seen)


# ---------------------------------------------------------------- GPU
@pytest.mark.gpu
def test_gpu_same_seed_same_reply_and_steering_changes_it():
    model, tok = qwen_critter.load_model()
    c = QwenCritter(model, tok)
    c.max_new_tokens = 24
    env = CritterWorld("stakes")
    env.reset(seed=990000)
    _, text = env.critter_view()
    ids = c._encode(read_system_prompt("stakes"), text)
    a = c.generate_from_ids(ids, 7, False)
    assert c.generate_from_ids(ids, 7, False) == a
    assert c.generate_from_ids(ids, 8, False) != a
    c.layer_norms = {18: 80.0}
    c.set_steering(steering.SteeringSpec(18, steering.random_unit_vector(1, model.config.hidden_size), 8))
    assert c.generate_from_ids(ids, 7, True) != a
