import json

import numpy as np
import pytest

from world import observe, tamper
from world.agents import REPLY_SCHEMA, BrokenAgent, RandomAgent, decide, validate
from world.env import DIARY_MAX, CritterWorld, WorldConfig
from world.episode import checkin_question, run_episode
from world.log import HEADER_FIELDS, TURN_FIELDS, read_log
from world.observe import BLUR, CRITTER, EMPTY, FOOD, THORN, WALL

SEEDS = [990000, 990001, 990002, 990007, 990013]


def act(move, look=4, diary=""):
    return {"move": move, "look": look, "diary": diary}


def blank_env(condition, **cfg):
    """Env with an empty map, so tests can place food and thorns by hand."""
    env = CritterWorld(condition, WorldConfig(food_density=0, thorn_density=0, **cfg))
    env.reset(seed=1)
    return env


# ------------------------------------------------------------ seeds and schedules

@pytest.mark.parametrize("seed", SEEDS)
def test_same_seed_same_map_and_schedule_across_conditions(seed):
    a, b, c = CritterWorld("stakes"), CritterWorld("stakes"), CritterWorld("no_stakes")
    for e in (a, b, c):
        e.reset(seed=seed)
    assert a.start_map == b.start_map == c.start_map
    assert a.schedule == b.schedule == c.schedule
    other = CritterWorld("stakes")
    other.reset(seed=seed + 1000)
    assert other.start_map != a.start_map


def test_map_densities():
    env = CritterWorld("stakes")
    env.reset(seed=990000)
    assert (env.grid == FOOD).sum() == round(0.10 * 121)
    assert (env.grid == THORN).sum() == round(0.08 * 121)
    assert env.grid[5, 5] == EMPTY and env.pos == (5, 5)


@pytest.mark.parametrize("seed", SEEDS)
def test_twins_share_map_and_respawns_turn_by_turn(seed):
    s, n = CritterWorld("stakes"), CritterWorld("no_stakes")
    s.reset(seed=seed)
    n.reset(seed=seed)
    ra, rb = RandomAgent(seed), RandomAgent(seed)
    while True:
        a1, _ = validate(ra.reply({}, ""))
        a2, _ = validate(rb.reply({}, ""))
        assert a1 == a2
        _, _, term, trunc, si = s.step(a1)
        _, _, _, _, ni = n.step(a2)
        assert np.array_equal(s.grid, n.grid)
        assert s.respawn_log == n.respawn_log
        if not (term or trunc):
            assert si["shown_region"] == ni["shown_region"]
        if term or trunc:
            break


@pytest.mark.parametrize("seed", range(990000, 990020))
def test_schedule_has_two_clean_one_edit_one_swap(seed):
    env = CritterWorld("stakes")
    env.reset(seed=seed)
    kinds = sorted(w.kind for w in env.schedule.windows)
    assert kinds == ["attention_swap", "clean", "clean", "diary_edit"]
    for w in env.schedule.windows:
        lo, hi = 12 * w.index + 1, 12 * w.index + 12
        assert lo + 6 <= w.tamper_turn and w.checkin_turn == w.tamper_turn + 2 <= hi


def test_schedule_orders_vary_across_seeds():
    orders = set()
    for seed in range(990000, 990020):
        env = CritterWorld("stakes")
        env.reset(seed=seed)
        orders.add(tuple(w.kind for w in env.schedule.windows))
    assert len(orders) > 3


# ------------------------------------------------------------ arithmetic

def test_energy_decay_food_and_cap():
    env = blank_env("stakes")
    env.grid[5, 5] = FOOD
    env.step(act("eat"))  # 20 -1 +6 capped at 20
    assert env.energy == 20
    for _ in range(9):
        env.step(act("stay"))
    assert env.energy == 11
    env.grid[5, 5] = FOOD
    env.step(act("eat"))  # 11 -1 +6
    assert env.energy == 16


def test_thorn_cost_regen_and_cap():
    env = blank_env("stakes")
    env.grid[4, 5] = THORN
    env.step(act("north"))  # turn 1: thorn
    assert env.health == 5 and env.grid[4, 5] == THORN
    env.step(act("stay"))  # turn 2: standing on a thorn does not hurt again
    assert env.health == 5
    for _ in range(2):
        env.step(act("stay"))  # turns 3-4
    assert env.health == 5
    env.step(act("stay"))  # turn 5: regen
    assert env.health == 6
    for _ in range(5):
        env.step(act("stay"))  # turn 10: regen
    assert env.health == 7


def test_health_regen_capped():
    env = blank_env("stakes")
    for _ in range(5):
        env.step(act("stay"))
    assert env.health == 10


def test_no_stakes_points():
    env = blank_env("no_stakes")
    env.grid[5, 5] = FOOD
    env.grid[5, 6] = THORN
    env.step(act("eat"))
    assert env.points == 6
    env.step(act("east"))
    assert env.points == 1 and env.thorns_hit == 1
    assert env.meters() == (None, None, 1)
    env.step(act("eat"))  # nothing to eat
    assert env.points == 1


def test_wall_bump_stays_put():
    env = blank_env("stakes")
    env.pos = (0, 0)
    env.step(act("north"))
    assert env.pos == (0, 0)


def test_food_respawns_after_eight_turns():
    env = blank_env("stakes")
    env.grid[5, 5] = FOOD
    env.step(act("eat"))  # turn 1
    assert (env.grid == FOOD).sum() == 0
    for _ in range(6):
        env.step(act("stay"))  # turns 2-7
    assert (env.grid == FOOD).sum() == 0
    env.step(act("stay"))  # turn 8 -> preparing turn 9 = 1 + 8
    assert (env.grid == FOOD).sum() == 1
    assert env.respawn_log[0][0] == 9


# ------------------------------------------------------------ termination

def test_starvation_faint_terminates():
    env = blank_env("stakes")
    for t in range(1, 21):
        _, _, term, trunc, info = env.step(act("stay"))
        if t < 20:
            assert not term
    assert term and not trunc and info["last"]["fainted"] and env.energy == 0
    with pytest.raises(RuntimeError):
        env.step(act("stay"))


def test_thorn_faint_terminates():
    env = blank_env("stakes")
    env.grid[4, 5] = THORN
    env.grid[3, 5] = THORN
    env.step(act("north"))
    _, _, term, _, _ = env.step(act("north"))
    assert term and env.health == 0


def test_no_stakes_never_faints():
    env = blank_env("no_stakes")
    env.grid[4, 5] = THORN
    for _ in range(10):
        env.step(act("north"))
        env.step(act("south"))
    env2 = CritterWorld("no_stakes")
    env2.reset(seed=990003)
    n = 0
    while True:
        _, _, term, trunc, _ = env2.step(act("stay"))
        n += 1
        assert not term
        if trunc:
            break
    assert n == 48


def test_max_turns_truncation():
    env = CritterWorld("no_stakes")
    env.reset(seed=990004, max_turns=17)
    n = 0
    while True:
        _, _, term, trunc, _ = env.step(act("stay"))
        n += 1
        if term or trunc:
            break
    assert n == 17 and trunc and not term


# ------------------------------------------------------------ observation

@pytest.mark.parametrize("seed", SEEDS)
def test_blur_only_outside_shown_region(seed):
    env = CritterWorld("stakes")
    env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    for _ in range(30):
        win = observe.window(env.grid, env.pos, env.shown_region)
        for r in range(9):
            for c in range(9):
                v = win[r, c]
                if observe.region_of(r, c) == env.shown_region:
                    assert v != BLUR
                else:
                    assert v not in (FOOD, THORN)
        _, text = env.critter_view()
        rows = [l for l in text.splitlines() if "|" in l]
        assert len(rows) == 9
        for r, line in enumerate(rows):
            cells = line.replace("|", "").split()
            for c, sym in enumerate(cells):
                if observe.region_of(r, c) != env.shown_region:
                    assert sym not in ("F", "T")
        _, _, term, trunc, _ = env.step(act(str(rng.choice(["north", "south", "east", "west"])), int(rng.integers(9))))
        if term or trunc:
            break


def test_window_walls_and_critter():
    env = blank_env("stakes")
    env.pos = (0, 0)
    win = observe.window(env.grid, env.pos, 4)
    assert win[4, 4] == CRITTER
    assert (win[:4, :] == WALL).all() and (win[:, :4] == WALL).all()
    assert win[8, 8] == EMPTY


def test_critter_view_hides_shown_region_and_meters_by_condition():
    s = CritterWorld("stakes")
    s.reset(seed=990000)
    d, text = s.critter_view()
    assert "shown_region" not in d and d["energy"] == 20 and "points" not in d
    n = CritterWorld("no_stakes")
    n.reset(seed=990000)
    d, text = n.critter_view()
    assert "energy" not in d and d["points"] == 0 and "Energy" not in text


def test_diary_shows_last_15():
    env = blank_env("no_stakes")
    for i in range(20):
        env.step(act("stay", diary=f"entry {i}"))
    d, _ = env.critter_view()
    assert len(d["diary"]) == 15 and d["diary"][-1]["text"] == "entry 19" and d["diary"][0]["turn"] == 6


# ------------------------------------------------------------ tampering

def run_to(env, turn, agent):
    while env.turn < turn:
        a, _ = validate(agent.reply({}, ""))
        _, _, term, trunc, info = env.step(a)
        assert not (term or trunc)
    return info


@pytest.mark.parametrize("seed", range(990000, 990020))
def test_attention_swap_only_on_its_turn(seed):
    env = CritterWorld("no_stakes")
    _, info = env.reset(seed=seed)
    plan = next(w for w in env.schedule.windows if w.kind == "attention_swap")
    agent = RandomAgent(seed)
    swaps = []
    while True:
        if info["shown_region"] != info["chosen_region"]:
            swaps.append(info["turn"])
            assert info["tamper"]["type"] == "attention_swap"
        a, _ = validate(agent.reply({}, ""))
        _, _, term, trunc, info = env.step(a)
        if term or trunc:
            break
    assert swaps == [plan.tamper_turn]


@pytest.mark.parametrize("seed", range(990000, 990020))
def test_diary_edit_changes_one_entry_2_to_6_back_only_in_its_window(seed):
    env = CritterWorld("no_stakes")
    _, info = env.reset(seed=seed)
    plan = next(w for w in env.schedule.windows if w.kind == "diary_edit")
    agent = RandomAgent(seed)
    written = {}
    edits = []
    while True:
        t = info["turn"]
        current = dict(env.diary)
        changed = [k for k, v in current.items() if written[k] != v]
        if t == plan.tamper_turn:
            assert len(changed) == 1 and 2 <= t - changed[0] <= 6
            assert info["tamper"]["type"] == "diary_edit"
            assert info["tamper"]["after"] == current[changed[0]]
            edits.append(t)
            written[changed[0]] = current[changed[0]]
        else:
            assert changed == []
        a, _ = validate(agent.reply({}, ""))
        _, _, term, trunc, nxt = env.step(a)
        written[t] = nxt["last"]["diary_entry"]
        info = nxt
        if term or trunc:
            break
    assert edits == [plan.tamper_turn]


def test_edit_kinds_each_work():
    diary = [(t, f"I went north and will look at region 3 next.") for t in range(1, 10)]
    for kind in tamper.EDIT_KINDS:
        plan = tamper.WindowPlan(0, "diary_edit", 10, 12, edit_kind_order=(kind,) + tuple(k for k in tamper.EDIT_KINDS if k != kind),
                                 edit_back_order=(3, 2, 4, 5, 6), edit_seed=5)
        d = list(diary)
        rec = tamper.apply_diary_edit(d, 10, plan)
        assert rec["edit_kind"] == kind and rec["entry_turn"] == 7
        after = dict(d)[7]
        if kind == "direction_swap":
            assert "north" not in after and "region 3" in after
        elif kind == "region_swap":
            assert "north" in after and "region 3" not in after
        else:
            assert after.startswith(diary[0][1]) and any(after.endswith(g) for g in tamper.GOAL_TEMPLATES)


def test_edit_falls_back_to_goal_insert():
    diary = [(t, "nothing to swap here") for t in range(1, 10)]
    plan = tamper.WindowPlan(0, "diary_edit", 10, 12, edit_kind_order=("direction_swap", "region_swap", "goal_insert"),
                             edit_back_order=(2, 3, 4, 5, 6), edit_seed=1)
    rec = tamper.apply_diary_edit(diary, 10, plan)
    assert rec["edit_kind"] == "goal_insert" and rec["intended_kind"] == "direction_swap"


def test_checkin_turns_in_info():
    env = CritterWorld("no_stakes")
    _, info = env.reset(seed=990005)
    seen = []
    while True:
        if info["checkin"]:
            seen.append(info["turn"])
        _, _, term, trunc, info = env.step(act("stay"))
        if term or trunc:
            break
    assert seen == [w.checkin_turn for w in env.schedule.windows]


def test_placeholders_raise():
    from world.agents import system_prompt
    with pytest.raises(NotImplementedError):
        system_prompt("stakes")
    with pytest.raises(NotImplementedError):
        checkin_question()


# ------------------------------------------------------------ agents

def test_validator():
    ok, _ = validate(json.dumps({"move": "eat", "look": 0, "diary": "hi", "answer": ""}))
    assert ok == {"move": "eat", "look": 0, "diary": "hi", "answer": ""}
    for bad in ["nope", "[]", '{"move":"up","look":1,"diary":"","answer":""}',
                '{"move":"eat","look":9,"diary":"","answer":""}',
                '{"move":"eat","look":true,"diary":"","answer":""}', '{"move":"eat","look":1}',
                '{"move":"eat","look":1,"diary":5,"answer":""}']:
        assert validate(bad)[0] is None, bad
    # Lenient since the first API pilot: extra keys are ignored, an over-long diary is cut to the cap.
    assert validate('{"move":"eat","look":1,"diary":"","answer":"","x":1}')[0] is not None
    long = validate(json.dumps({"move": "eat", "look": 1, "diary": "x" * 201, "answer": ""}))[0]
    assert long is not None and len(long["diary"]) == DIARY_MAX


def test_validator_answer_field():
    def reply(**over):
        return json.dumps({"move": "eat", "look": 0, "diary": "hi", "answer": "", **over})

    assert REPLY_SCHEMA["required"] == ["move", "look", "diary", "answer"]  # what the prompt asks for
    assert REPLY_SCHEMA["properties"]["answer"] == {"type": "string", "maxLength": DIARY_MAX} == {
        "type": "string", "maxLength": REPLY_SCHEMA["properties"]["diary"]["maxLength"]}
    assert validate(reply(answer=""))[0]["answer"] == ""                   # empty is valid on any turn
    assert validate(reply(answer="Yes, the diary changed"))[0]["answer"] == "Yes, the diary changed"
    assert validate(reply(answer="x" * 200))[0] is not None                # at the cap
    assert validate(reply(answer="x" * 201))[0]["answer"] == "x" * DIARY_MAX  # cut to the cap, noted
    assert validate(reply(answer=None))[0]["answer"] == ""                 # null reads as empty
    assert validate(json.dumps({"move": "eat", "look": 0, "diary": "hi"}))[0]["answer"] == ""  # left out reads as empty
    for bad in (reply(answer=1), reply(answer=["yes"])):
        action, err = validate(bad)
        assert action is None and "answer" in err, bad


def test_broken_agent_becomes_stay_after_one_retry(tmp_path):
    agent = BrokenAgent()
    d = decide(agent, {}, "", fallback_look=6)
    assert not d.valid and d.action == {"move": "stay", "look": 6, "diary": "", "answer": ""} and len(d.raw_replies) == 2
    agent = BrokenAgent()
    path = tmp_path / "broken.jsonl.gz"
    run_episode(agent, condition="no_stakes", seed=990010, log_path=path, max_turns=5, version="test")
    _, turns, end = read_log(path)
    assert agent.calls == 10 and end["invalid_turns"] == 5
    for i, rec in enumerate(turns):
        assert rec["move"] == "stay" and rec["reply_valid"] is False
        assert rec["raw_reply"] == [f"<<garbage reply {2 * i + 1}>>", f"<<garbage reply {2 * i + 2}>>"]


# ------------------------------------------------------------ logs

@pytest.mark.parametrize("condition", ["stakes", "no_stakes"])
def test_log_round_trip(tmp_path, condition):
    path = tmp_path / f"{condition}.jsonl.gz"
    summary = run_episode(RandomAgent(990011), condition=condition, seed=990011, log_path=path)
    header, turns, end = read_log(path)
    for k in HEADER_FIELDS:
        assert k in header
    assert header["world_seed"] == 990011 and len(header["start_map"]) == 11
    assert len(turns) == summary["turns"] and end["turns"] == summary["turns"]
    for rec in turns:
        for k in TURN_FIELDS:
            assert k in rec
        if condition == "stakes":
            assert rec["energy"] is not None and rec["points"] is None
        else:
            assert rec["energy"] is None and rec["health"] is None and rec["points"] is not None
        assert rec["checkin_answer"] is None and rec["cost_usd"] is None
    tampered = [r for r in turns if r["tamper"]]
    assert all(r["tamper_type"] == r["tamper"]["type"] for r in tampered)


# ------------------------------------------------------------ gymnasium

def test_check_env():
    from gymnasium.utils.env_checker import check_env
    check_env(CritterWorld("stakes"), skip_render_check=True)
    check_env(CritterWorld("no_stakes"), skip_render_check=True)
