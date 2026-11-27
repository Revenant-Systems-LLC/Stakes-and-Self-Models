import json

import pytest

from runner import plan
from runner.config import ConfigError
from runner.fake_client import error, garbage, refusal, valid_reply
from runner.ledger import Ledger, PriceError, PriceTable, Usage
from runner.play import play_episode, parse_yes_no
from runner.plan import RunnerError
from runner.run import main
from runner.tests.helpers import (MODELS, PRICE_FILE, QUESTION, all_files, make_config, make_runner, manifest,
                                  read_gz_lines, stay_script)
from world.agents import RandomAgent
from world.episode import run_episode
from world.log import read_log


def sub(tmp_path, name):
    d = tmp_path / name
    d.mkdir()
    return d


def episodes(cfg, phase="dev"):
    return [r for r in manifest(cfg, phase) if r["type"] == "episode"]


# ---------------------------------------------------------------- twin pairing
def test_stakes_twin_first_and_no_stakes_twin_ends_on_the_stakes_twins_last_turn(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 2})
    report = make_runner(cfg, tiers=["haiku"], script=stay_script()).run()
    assert report.stop is None and report.pairs_done == 2
    eps = episodes(cfg)
    assert [e["condition_code"] for e in eps] == ["stakes", "no_stakes", "stakes", "no_stakes"]  # stakes first, every pair
    for stakes, nostakes in zip(eps[::2], eps[1::2]):
        assert stakes["seed"] == nostakes["seed"]
        _, st, st_end = read_log(stakes["log_path"])
        _, ns, ns_end = read_log(nostakes["log_path"])
        assert st_end["fainted"] and st_end["turns"] == 20 == len(st)  # a critter that never eats faints on turn 20
        assert ns_end["turns"] == 20 == len(ns) and not ns_end["fainted"]  # no-stakes stopped on that same turn
        assert [t["turn"] for t in ns] == [t["turn"] for t in st]


def test_the_check_in_question_is_added_on_check_in_turns_only(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    runner = make_runner(cfg, tiers=["haiku"], script=stay_script())
    runner.run()
    asked = sum(QUESTION in c["messages"][0]["content"] for c in runner.client.calls)
    checkins = 0
    for e in episodes(cfg):
        _, turns, _ = read_log(e["log_path"])
        checkins += sum(t["checkin"] for t in turns)
        for t in turns:
            assert (t["checkin_answer"] is not None) == t["checkin"]  # the diary line of a check-in turn is the answer
    assert asked == checkins > 0


def test_check_in_answer_is_the_diary_text_and_yes_no_is_parsed_from_it(tmp_path):
    assert parse_yes_no("Yes, my diary line changed") is True
    assert parse_yes_no("  no. nothing") is False
    assert parse_yes_no('"No"') is False
    assert parse_yes_no("nothing seems off") is None and parse_yes_no("not sure") is None and parse_yes_no(None) is None

    cfg = make_config(tmp_path, pairs={"haiku": 1})
    runner = make_runner(cfg, tiers=["haiku"], script=lambda kw: valid_reply("stay", 4, "Yes, something was off"))
    runner.run()
    _, turns, _ = read_log(episodes(cfg)[0]["log_path"])
    answered = [t for t in turns if t["checkin"]]
    assert answered and all(t["checkin_answer"] == "Yes, something was off" and t["checkin_yes"] is True for t in answered)


def test_pair_order_across_tiers_is_shuffled_by_a_fixed_seed():
    counts = {"haiku": 4, "sonnet": 4, "opus": 3}
    a = plan.build_slots(counts, 11)
    assert a == plan.build_slots(counts, 11)  # fixed by the seed
    assert a != plan.build_slots(counts, 12)
    assert sorted(a) == sorted((t, k) for t, n in counts.items() for k in range(n))
    assert [t for t, _ in a] != sorted(t for t, _ in a)  # mixed, not tier by tier


def test_the_runner_follows_the_shuffled_order_and_a_tier_subset_keeps_it(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 2, "sonnet": 2, "opus": 2}, shuffle_seed=3)
    make_runner(cfg).run()
    ran = [(e["tier"]) for e in episodes(cfg)[::2]]
    assert ran == [t for t, _ in plan.build_slots({"haiku": 2, "sonnet": 2, "opus": 2}, 3)]
    subset = make_config(sub(tmp_path, "subset"), pairs={"haiku": 2, "sonnet": 2, "opus": 2}, shuffle_seed=3)
    make_runner(subset, tiers=["opus", "haiku"]).run()
    assert [e["tier"] for e in episodes(subset)[::2]] == [t for t, _ in plan.build_slots({"haiku": 2, "sonnet": 2, "opus": 2}, 3) if t != "sonnet"]


def test_limit_pairs_can_only_lower_the_plan(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 3})
    report = make_runner(cfg, tiers=["haiku"], limit_pairs=1).run()
    assert report.pairs_done == 1
    over = make_config(sub(tmp_path, "over"), pairs={"haiku": 2})
    assert make_runner(over, tiers=["haiku"], limit_pairs=50).run().pairs_done == 2  # the plan, not 50


# ---------------------------------------------------------------- seeds
def test_dev_seeds_are_refused_in_pilot_confirmatory_and_reserve(tmp_path):
    for phase in ("pilot", "confirmatory", "reserve"):
        d = sub(tmp_path, phase)
        cfg = make_config(d, seed_lists={"dev": [990000, 990001], phase: [1, 2, 990199, 3]})
        runner = make_runner(cfg, phase, tiers=["haiku"])
        with pytest.raises(RunnerError, match="refuses dev seeds"):
            runner.run()
        assert runner.client.calls == [] and not cfg.runs_dir.exists()


def test_the_edges_of_the_dev_range(tmp_path):
    plan.check_phase_seeds("pilot", [989999, 990200])  # just outside the range: fine
    for edge in (990000, 990199):
        with pytest.raises(RunnerError):
            plan.check_phase_seeds("pilot", [edge])
    plan.check_phase_seeds("dev", [990000, 990199])
    with pytest.raises(RunnerError, match="only use dev seeds"):
        plan.check_phase_seeds("dev", [990000, 5])  # a dev run may not burn a real seed


def test_dev_seeds_through_the_command_line_are_refused_too(tmp_path, capsys):
    cfg = make_config(tmp_path, seed_lists={"dev": [990000, 990001], "pilot": [990100, 1]}, pairs={"haiku": 1, "sonnet": 0, "opus": 0})
    assert main(["--phase", "pilot", "--client", "fake", "--config", str(cfg.source), "--no-progress", "--key-expires", "2099-01-01T00:00+00:00"]) == 2
    assert "refuses dev seeds" in capsys.readouterr().err and not cfg.runs_dir.exists()


def test_phases_never_share_seeds(tmp_path):
    cfg = make_config(tmp_path, seed_lists={"dev": [990000], "pilot": [1, 2, 3], "confirmatory": [3, 4, 5]})
    with pytest.raises(RunnerError, match="both the confirmatory and pilot"):
        make_runner(cfg, "confirmatory", tiers=["haiku"]).run()


def test_seed_list_file_rules(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("# c\n5\n\n6  # six\n7\n", encoding="utf-8")
    assert plan.read_seed_list(f) == [5, 6, 7]
    f.write_text("1\n1\n", encoding="utf-8")
    with pytest.raises(RunnerError, match="repeated"):
        plan.read_seed_list(f)
    f.write_text("x\n", encoding="utf-8")
    with pytest.raises(RunnerError, match="not an integer"):
        plan.read_seed_list(f)
    with pytest.raises(RunnerError, match="missing"):
        plan.read_seed_list(tmp_path / "nope.txt")


# ---------------------------------------------------------------- exclusions
def test_an_api_failure_excludes_the_pair_and_both_twins_rerun_on_the_next_seed(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    state = {"no_stakes_calls": 0}

    def script(kw):
        if "no_stakes" in kw["system"]:
            state["no_stakes_calls"] += 1
            if state["no_stakes_calls"] == 1:  # the very first no-stakes call, on the first seed, fails for good
                return error(400, "bad request")
        return valid_reply("stay")

    lines = []
    runner = make_runner(cfg, tiers=["haiku"], script=script, lines=lines)
    report = runner.run()
    seeds = list(range(990000, 990020))
    assert report.stop is None and report.pairs_done == 1 and report.exclusions == [("haiku", seeds[0], "no_stakes: api_failure")]

    m = manifest(cfg)
    assert [(r["seed"], r["condition_code"], r["status"]) for r in m if r["type"] == "episode"] == [
        (seeds[0], "stakes", "done"), (seeds[0], "no_stakes", "api_failure"),   # first seed: stakes ok, twin failed
        (seeds[1], "stakes", "done"), (seeds[1], "no_stakes", "done"),          # replacement: both twins rerun
    ]
    assert {"type": "pair_excluded", "tier": "haiku", "seed": seeds[0]}.items() <= next(r for r in m if r["type"] == "pair_excluded").items()
    # the failed twin's log ends deliberately, with the error recorded
    failed = next(r for r in m if r["status"] == "api_failure")
    _, _, end = read_log(failed["log_path"])
    assert end["status"] == "api_failure" and end["error"]["status_codes"] == [400] and end["turns"] == 0
    assert any("EXCLUDED" in l for l in lines)


def test_a_harness_crash_is_excluded_and_replaced_and_leaves_no_end_line(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    n = {"i": 0}

    def script(kw):
        n["i"] += 1
        if n["i"] == 3:
            raise RuntimeError("harness bug")
        return valid_reply("stay")

    report = make_runner(cfg, tiers=["haiku"], script=script).run()
    assert report.pairs_done == 1 and report.exclusions == [("haiku", 990000, "stakes: crash")]
    crashed = next(r for r in episodes(cfg) if r["status"] == "crash")
    assert "RuntimeError" in crashed["error"]
    header, turns, end = read_log(crashed["log_path"])
    assert end is None and len(turns) == 2  # no end line: a crash is easy to spot, as world/log.py says


def test_exclusions_in_a_row_stop_the_run(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 5}, max_consecutive_exclusions=3)
    report = make_runner(cfg, tiers=["haiku"], script=lambda kw: error(400, "nope")).run()
    assert report.stop == "exclusions" and report.exit_code == 4 and len(report.exclusions) == 3


def test_running_out_of_seeds_stops_the_run(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 2}, seed_lists={"dev": [990000, 990001], "pilot": [1], "confirmatory": [2], "reserve": [3]})
    # two planned pairs, two seeds, and the first pair is excluded: the replacement would be a third seed
    calls = {"n": 0}

    def script(kw):
        calls["n"] += 1
        return error(400, "x") if calls["n"] == 1 else valid_reply("stay")

    report = make_runner(cfg, tiers=["haiku"], script=script).run()
    assert report.stop == "seed_list" and report.exit_code == 4


# ---------------------------------------------------------------- bad replies at the episode level
def test_refusals_and_garbage_are_bad_replies_that_stay_and_are_logged(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    steps = [refusal(), refusal(), garbage("<<g1>>"), garbage("<<g2>>")]  # turn 1 refused twice, turn 2 garbled twice
    calls = {"i": 0}

    def script(kw):
        i = calls["i"]
        calls["i"] += 1
        return steps[i] if i < len(steps) else valid_reply("stay")

    make_runner(cfg, tiers=["haiku"], script=script).run()
    stakes = episodes(cfg)[0]
    _, turns, end = read_log(stakes["log_path"])
    assert [t["reply_valid"] for t in turns[:3]] == [False, False, True]
    assert turns[0]["move"] == "stay" and len(turns[0]["reply_errors"]) == 2 and turns[0]["raw_reply"] == ["", ""]
    assert turns[1]["raw_reply"] == ["<<g1>>", "<<g2>>"]
    assert [c["stop_reason"] for c in turns[0]["calls"]] == ["refusal", "refusal"]
    assert turns[0]["calls"][0]["stop_details"]["category"] == "general_harms"
    assert end["invalid_turns"] == 2 and end["refusals"] == 2 and stakes["status"] == "done"  # counted, episode kept


# ---------------------------------------------------------------- end to end
def test_a_short_fake_run_writes_logs_that_world_log_reads_back(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1, "sonnet": 1, "opus": 1})
    report = make_runner(cfg).run()
    assert report.stop is None and report.pairs_done == 3 and report.exit_code == 0
    eps = episodes(cfg)
    assert len(eps) == 6 and all(e["status"] == "done" for e in eps)
    led = Ledger(cfg.runs_dir, "dev", 10, PriceTable.load(cfg.price_file))
    prices = PriceTable.load(PRICE_FILE)
    total_from_logs = 0.0
    for stakes, nostakes in zip(eps[::2], eps[1::2]):
        assert stakes["turns"] == nostakes["turns"]  # the twin ends on its stakes twin's last turn
    for e in eps:
        header, turns, end = read_log(e["log_path"])
        assert header["arm"] == "arm1" and header["model"] == MODELS[e["tier"]] and header["world_seed"] == e["seed"]
        assert header["condition_code"] == e["condition_code"] and len(header["start_map"]) == 11
        assert header["tier"] == e["tier"] and header["phase"] == "dev" and header["code_version"] == "t"
        assert end["status"] == "done" and end["turns"] == len(turns) and turns
        assert all(t["tokens_in"] > 0 and t["tokens_out"] > 0 and t["cost_usd"] > 0 for t in turns)
        assert sum(t["cost_usd"] for t in turns) == pytest.approx(end["cost_usd"])
        assert sum(t["tokens_out"] for t in turns) == end["tokens_out"]
        total_from_logs += end["cost_usd"]
    assert led.spend == pytest.approx(total_from_logs)
    lines = [json.loads(l) for l in led.path.read_text(encoding="utf-8").splitlines()]
    assert sum(l["cost_usd"] for l in lines if l["type"] == "response") == pytest.approx(led.spend)
    assert sum(1 for l in lines if l["type"] == "episode_end") == 6
    first = next(l for l in lines if l["type"] == "response")
    assert prices.cost(first["model"], Usage(first["input_tokens"], first["output_tokens"])) == pytest.approx(first["cost_usd"])


def test_play_episode_matches_world_run_episode_apart_from_the_runners_extra_fields(tmp_path):
    seed = 990003
    ref = run_episode(RandomAgent(seed), condition="stakes", seed=seed, log_path=tmp_path / "ref.gz", version="t")
    mine = play_episode(RandomAgent(seed), condition="stakes", seed=seed, log_path=tmp_path / "mine.gz", model="random",
                        condition_code="stakes", version="t")["summary"]
    h1, t1, e1 = read_log(tmp_path / "ref.gz")
    h2, t2, e2 = read_log(tmp_path / "mine.gz")
    assert h1["start_map"] == h2["start_map"] and h1["world_seed"] == h2["world_seed"] == seed
    assert len(t1) == len(t2)
    differs = {"checkin_answer", "tokens_in", "tokens_out", "cost_usd"}
    for a, b in zip(t1, t2):
        assert {k: v for k, v in a.items() if k not in differs} == {k: b[k] for k in a if k not in differs}
    assert {k: v for k, v in ref.items()} == {k: mine[k] for k in ref}


def test_play_episode_will_not_overwrite_a_log(tmp_path):
    p = tmp_path / "a.gz"
    play_episode(RandomAgent(1), condition="stakes", seed=990001, log_path=p, model="r", condition_code="stakes", version="t")
    with pytest.raises(FileExistsError):
        play_episode(RandomAgent(1), condition="stakes", seed=990001, log_path=p, model="r", condition_code="stakes", version="t")


def test_a_rerun_skips_finished_episodes_and_spends_nothing_more(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 2})
    make_runner(cfg, tiers=["haiku"]).run()
    spent = Ledger(cfg.runs_dir, "dev", 10, PriceTable.load(PRICE_FILE)).spend
    again = make_runner(cfg, tiers=["haiku"])
    report = again.run()
    assert report.pairs_done == 2 and again.client.calls == [] and report.episodes_run == 0
    assert Ledger(cfg.runs_dir, "dev", 10, PriceTable.load(PRICE_FILE)).spend == pytest.approx(spent)


def test_an_orphan_log_from_a_hard_stop_excludes_its_pair(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    orphan = cfg.runs_dir / "dev" / "logs" / "haiku" / "990000-stakes.jsonl.gz"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"")  # an interrupted episode: a log file but no manifest line
    report = make_runner(cfg, tiers=["haiku"]).run()
    assert report.pairs_done == 1 and report.exclusions[0][:2] == ("haiku", 990000)
    assert {e["seed"] for e in episodes(cfg)} == {990001}
    assert orphan.exists()  # never deleted or overwritten


# ---------------------------------------------------------------- blinding, files, prices
def test_confirmatory_runs_use_the_blinded_codes_everywhere_the_dashboard_could_look(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    key = tmp_path / "key" / "blinding_key.json"
    make_runner(cfg, "confirmatory", tiers=["haiku"], key_path=key).run()
    codes = json.loads(key.read_text(encoding="utf-8"))
    for e in episodes(cfg, "confirmatory"):
        header, _, _ = read_log(e["log_path"])
        assert header["condition_code"] in codes.values()
    visible = [p.name for p in all_files(cfg.runs_dir / "confirmatory" / "logs")]
    ledger_text = (cfg.runs_dir / "ledger" / "confirmatory.jsonl").read_text(encoding="utf-8")
    header_text = json.dumps(read_log(episodes(cfg, "confirmatory")[0]["log_path"])[0])
    for text in visible + [ledger_text, header_text]:
        assert "stakes" not in str(text).lower()


@pytest.mark.parametrize("missing", ["stakes", "no_stakes", "checkin_question", "seeds"])
def test_missing_prompt_question_or_seed_files_are_clear_errors_and_nothing_is_written(tmp_path, missing):
    cfg = make_config(tmp_path, skip=(missing,))
    runner = make_runner(cfg, tiers=["haiku"])
    with pytest.raises((ConfigError, RunnerError), match="missing"):
        runner.run()
    assert runner.client.calls == [] and not cfg.runs_dir.exists()


def test_the_runner_refuses_to_start_without_a_price_for_the_model_it_runs(tmp_path):
    raw = json.loads(PRICE_FILE.read_text(encoding="utf-8"))
    del raw["models"]["claude-opus-5-5"]
    pf = tmp_path / "prices.json"
    pf.write_text(json.dumps(raw), encoding="utf-8")
    cfg = make_config(tmp_path, price_file=pf)
    runner = make_runner(cfg, tiers=["opus"])
    with pytest.raises(PriceError, match="claude-opus-5-5"):
        runner.run()
    assert runner.client.calls == [] and not cfg.runs_dir.exists()
    make_runner(cfg, tiers=["haiku"], limit_pairs=1).run()  # a tier that has a price still runs


def test_an_empty_plan_is_refused(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 0, "sonnet": 0, "opus": 0})
    with pytest.raises(RunnerError, match="plans no pairs"):
        make_runner(cfg).run()


def test_the_command_line_runs_a_dev_phase_on_the_fake_client(tmp_path, capsys):
    cfg = make_config(tmp_path, pairs={"haiku": 1, "sonnet": 0, "opus": 0})
    assert main(["--phase", "dev", "--config", str(cfg.source), "--no-progress"]) == 0
    out = capsys.readouterr().out
    assert "MODE: fake client only" in out and "finished: 1 pairs" in out
    assert len(episodes(cfg)) == 2
