"""Tests for job 005: own-cell line, GreedyAgent, blinded condition codes."""

import json

import pytest

from world import blinding
from world.agents import GreedyAgent, RandomAgent, validate
from world.env import CritterWorld, WorldConfig
from world.episode import run_episode
from world.log import read_log
from world.observe import FOOD, THORN


def act(move, look=4, diary=""):
    return {"move": move, "look": look, "diary": diary}


def blank_env(condition="stakes"):
    env = CritterWorld(condition, WorldConfig(food_density=0, thorn_density=0))
    env.reset(seed=1)
    return env


def obs_with(cells, own="nothing"):
    """A structured observation with an empty 9x9 window plus the given cells."""
    rows = [["."] * 9 for _ in range(9)]
    rows[4][4] = "@"
    for (r, c), sym in cells.items():
        rows[r][c] = sym
    return {"window": ["".join(r) for r in rows], "own_cell": own, "diary": []}


# ------------------------------------------------------------ own cell

@pytest.mark.parametrize("condition", ["stakes", "no_stakes"])
def test_own_cell_food_and_nothing(condition):
    env = blank_env(condition)
    d, text = env.critter_view()
    assert d["own_cell"] == "nothing" and "Your cell: nothing" in text
    env.grid[4, 5] = FOOD
    env.step(act("north"))
    d, text = env.critter_view()
    assert d["own_cell"] == "food" and "Your cell: food" in text
    assert env._obs()["own_cell"] == FOOD
    env.step(act("eat"))
    d, text = env.critter_view()
    assert d["own_cell"] == "nothing" and "Your cell: nothing" in text


def test_own_cell_thorn_only_on_the_turn_stepped_on():
    env = blank_env()
    env.grid[5, 6] = THORN
    env.step(act("east"))
    d, text = env.critter_view()
    assert d["own_cell"] == "thorn" and "Your cell: thorn" in text
    assert env._obs()["own_cell"] == THORN
    env.step(act("stay"))
    d, text = env.critter_view()
    assert d["own_cell"] == "nothing" and env._obs()["own_cell"] == 0


def test_own_cell_line_is_a_plain_fact_outside_the_map():
    env = blank_env()
    _, text = env.critter_view()
    line = [l for l in text.splitlines() if l.startswith("Your cell:")]
    assert line == ["Your cell: nothing"]
    assert sum("|" in l for l in text.splitlines()) == 9


# ------------------------------------------------------------ greedy agent

def test_greedy_eats_when_on_food():
    a, _ = validate(GreedyAgent(0).reply(obs_with({}, own="food"), ""))
    assert a["move"] == "eat"


def test_greedy_walks_to_nearest_visible_food():
    a, _ = validate(GreedyAgent(0).reply(obs_with({(4, 7): "F", (0, 0): "F"}), ""))
    assert a["move"] == "east"


def test_greedy_routes_around_a_seen_thorn():
    for seed in range(10):
        a, _ = validate(GreedyAgent(seed).reply(obs_with({(4, 5): "T", (4, 6): "F"}), ""))
        assert a["move"] in ("north", "south")


def test_greedy_prefers_clear_path_over_blur():
    cells = {(3, 4): "?", (2, 4): "F", (4, 3): "?", (4, 5): "?"}
    a, _ = validate(GreedyAgent(0).reply(obs_with(cells), ""))
    assert a["move"] == "south"  # the only route that does not step onto blur first


def test_greedy_looks_at_most_blurred_region_without_food():
    cells = {(7, 7): "?", (7, 8): "?", (8, 8): "?", (0, 0): "?"}
    for seed in range(10):
        a, _ = validate(GreedyAgent(seed).reply(obs_with(cells), ""))
        assert a["look"] == 8 and a["move"] in ("south", "east")


def test_greedy_never_steps_onto_a_seen_thorn():
    cells = {(3, 4): "T", (5, 4): "T", (4, 3): "T", (4, 5): "T"}
    a, _ = validate(GreedyAgent(0).reply(obs_with(cells), ""))
    assert a["move"] == "stay"


@pytest.mark.parametrize("seed", [990000, 990001, 990002])
def test_greedy_valid_and_deterministic(tmp_path, seed):
    s1 = run_episode(GreedyAgent(seed), condition="stakes", seed=seed, log_path=tmp_path / "a.jsonl.gz", version="t")
    s2 = run_episode(GreedyAgent(seed), condition="stakes", seed=seed, log_path=tmp_path / "b.jsonl.gz", version="t")
    assert s1["invalid_turns"] == 0
    _, t1, _ = read_log(tmp_path / "a.jsonl.gz")
    _, t2, _ = read_log(tmp_path / "b.jsonl.gz")
    assert [t["move"] for t in t1] == [t["move"] for t in t2]
    assert s1 == s2


def test_greedy_outforages_random(tmp_path):
    seeds = range(990000, 990010)
    g = [run_episode(GreedyAgent(s), condition="stakes", seed=s, log_path=tmp_path / f"g{s}.gz", version="t") for s in seeds]
    r = [run_episode(RandomAgent(s), condition="stakes", seed=s, log_path=tmp_path / f"r{s}.gz", version="t") for s in seeds]
    assert sum(x["food_eaten"] for x in g) > 3 * sum(x["food_eaten"] for x in r)
    assert sum(x["turns"] for x in g) > sum(x["turns"] for x in r)


# ------------------------------------------------------------ blinding

def test_blinding_codes_differ_and_stay_fixed(tmp_path):
    key = tmp_path / "key.json"
    k1 = blinding.load_key(key)
    assert k1["stakes"] != k1["no_stakes"]
    before = key.read_bytes()
    for _ in range(3):
        assert blinding.load_key(key) == k1
        assert blinding.condition_code("stakes", blinded=True, path=key) == k1["stakes"]
        assert blinding.condition_code("no_stakes", blinded=True, path=key) == k1["no_stakes"]
    assert key.read_bytes() == before


def test_blinding_never_overwrites_an_existing_key(tmp_path):
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"stakes": "C-AAAAAA", "no_stakes": "C-BBBBBB"}), encoding="utf-8")
    assert blinding.load_key(key) == {"stakes": "C-AAAAAA", "no_stakes": "C-BBBBBB"}


def test_blinding_refuses_a_key_inside_the_repo():
    with pytest.raises(ValueError):
        blinding.key_path(blinding.REPO_ROOT / "world" / "key.json")
    assert blinding.REPO_ROOT not in blinding.DEFAULT_KEY_PATH.resolve().parents


def test_blinding_path_from_env_var(tmp_path, monkeypatch):
    key = tmp_path / "env_key.json"
    monkeypatch.setenv(blinding.ENV_VAR, str(key))
    blinding.load_key()
    assert key.exists()


def test_unblinded_uses_plain_names(tmp_path):
    key = tmp_path / "key.json"
    assert blinding.condition_code("stakes", blinded=False, path=key) == "stakes"
    assert blinding.condition_code("no_stakes", blinded=False, path=key) == "no_stakes"
    assert not key.exists()


@pytest.mark.parametrize("seed", [990000, 990003])
def test_blinded_log_headers_hide_condition_names(tmp_path, seed):
    key = tmp_path / "key.json"
    codes = set()
    for condition in ("stakes", "no_stakes"):
        path = tmp_path / f"{condition}.jsonl.gz"
        run_episode(RandomAgent(seed), condition=condition, seed=seed, log_path=path, version="t",
                    blinded=True, key_path=key, max_turns=5)
        header, _, _ = read_log(path)
        code = header["condition_code"]
        assert "stakes" not in code.lower() and "no_stakes" not in code.lower()
        codes.add(code)
        pilot = tmp_path / f"pilot_{condition}.jsonl.gz"
        run_episode(RandomAgent(seed), condition=condition, seed=seed, log_path=pilot, version="t", max_turns=5)
        assert read_log(pilot)[0]["condition_code"] == condition
    assert codes == set(blinding.load_key(key).values())


def test_blinded_run_rejects_a_caller_code(tmp_path):
    with pytest.raises(ValueError):
        run_episode(RandomAgent(1), condition="stakes", seed=1, log_path=tmp_path / "x.gz", version="t",
                    blinded=True, key_path=tmp_path / "k.json", condition_code="stakes")
