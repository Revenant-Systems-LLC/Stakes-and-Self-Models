"""The exploratory tiers phase (Fable and Mythos), fake client only."""

import json

import pytest

from runner import plan
from runner.config import ConfigError, load_config
from runner.ledger import Ledger, PriceError, PriceTable
from runner.tests.helpers import MODELS, PRICE_FILE, make_config, make_runner, manifest, stay_script
from world.log import read_log


def episodes(cfg, phase="tiers"):
    return [r for r in manifest(cfg, phase) if r["type"] == "episode"]


# ---------------------------------------------------------------- the order
def test_the_alternate_order_goes_fable_mythos_fable_mythos():
    got = plan.build_slots({"fable": 3, "mythos": 3}, 1, "alternate")
    assert got == [("fable", 0), ("mythos", 0), ("fable", 1), ("mythos", 1), ("fable", 2), ("mythos", 2)]
    assert got == plan.build_slots({"fable": 3, "mythos": 3}, 999, "alternate")  # no seed in it
    assert plan.build_slots({"fable": 3, "mythos": 2}, 1, "alternate")[-1] == ("fable", 2)  # a longer tier just finishes


def test_the_shuffled_order_of_the_three_preregistered_tiers_did_not_change():
    # Adding the two tiers must not move the confirmatory shuffle: same slots, same fixed seed, same order as before.
    counts = {"haiku": 400, "sonnet": 400, "opus": 250}
    old = [(t, k) for t in ("haiku", "sonnet", "opus") for k in range(counts[t])]
    import random
    random.Random(20261126).shuffle(old)
    assert plan.build_slots({**counts, "fable": 0, "mythos": 0}, 20261126) == old
    assert plan.build_slots(counts, 20261126) == old


def test_a_bad_order_is_refused_in_the_plan_and_in_the_config(tmp_path):
    with pytest.raises(plan.RunnerError):
        plan.build_slots({"fable": 1}, 1, "random")
    cfg = make_config(tmp_path)
    raw = json.loads(cfg.source.read_text(encoding="utf-8"))
    raw["phases"]["tiers"]["order"] = "random"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ConfigError, match="order must be one of"):
        load_config(bad)
    raw["phases"]["tiers"]["order"] = "alternate"
    raw["phases"]["tiers"]["pairs_per_tier"]["gemini"] = 3
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown tiers"):
        load_config(bad)


# ---------------------------------------------------------------- the dry run
def test_a_tiers_dry_run_plays_two_pairs_stakes_first_on_the_same_world(tmp_path):
    cfg = make_config(tmp_path, pairs={"fable": 1, "mythos": 1})
    lines = []
    report = make_runner(cfg, "tiers", script=stay_script(), lines=lines).run()
    assert report.stop is None and report.pairs_done == 2 and report.episodes_run == 4 and report.exit_code == 0
    eps = episodes(cfg)
    assert [(e["tier"], e["condition_code"], e["status"]) for e in eps] == [
        ("fable", "stakes", "done"), ("fable", "no_stakes", "done"),
        ("mythos", "stakes", "done"), ("mythos", "no_stakes", "done")]
    assert {e["seed"] for e in eps} == {4000}                      # both models play the first seed of tiers.txt
    for e in eps:
        header, turns, end = read_log(e["log_path"])
        assert header["model"] == MODELS[e["tier"]] and header["phase"] == "tiers"
        assert header["condition_code"] == e["condition_code"]       # tiers is exploratory: real condition names
        assert end["status"] == "done" and end["turns"] == 20
    assert any("2 pairs planned" in l and "'fable': 1" in l and "'mythos': 1" in l for l in lines)


def test_tiers_spend_is_priced_from_the_fable_and_mythos_rates_and_booked_to_its_own_ledger(tmp_path):
    cfg = make_config(tmp_path, pairs={"fable": 1, "mythos": 1})
    make_runner(cfg, "tiers", script=stay_script()).run()
    per_call = (1000 * 8.0 + 100 * 40.0) / 1e6      # the fake reply: 1,000 tokens in, 100 out
    led = Ledger(cfg.runs_dir, "tiers", 150, PriceTable.load(PRICE_FILE))
    assert led.spend == pytest.approx(80 * per_call)  # 4 episodes of 20 turns
    assert led.cap == 150
    assert (cfg.runs_dir / "ledger" / "tiers.jsonl").exists()
    assert not (cfg.runs_dir / "ledger" / "reserve.jsonl").exists()
    assert not (cfg.runs_dir / "ledger" / "dev.jsonl").exists()


def test_a_cap_hit_cannot_wipe_out_one_model(tmp_path):
    # $0.24 an episode, 2 x $0.48 a pair. A $3.00 cap runs out part way through the plan; the alternating order means
    # the two models are never more than one pair apart when it does.
    cfg = make_config(tmp_path, pairs={"fable": 10, "mythos": 10}, caps={"tiers": 3.0}, priors={"fable": 0.3, "mythos": 0.3})
    report = make_runner(cfg, "tiers", script=stay_script()).run()
    assert report.stop == "cap"
    done = {t: sum(1 for e in episodes(cfg) if e["tier"] == t and e["condition_code"] == "no_stakes" and e["status"] == "done")
            for t in ("fable", "mythos")}
    assert 0 < sum(done.values()) < 20 and abs(done["fable"] - done["mythos"]) <= 1


def test_tiers_uses_the_models_priors_before_a_model_has_finished_an_episode(tmp_path):
    # Prior $1.30: a first episode needs spend + 2 x 1.30 <= cap. A $2.50 cap refuses it before any call.
    cfg = make_config(tmp_path, pairs={"fable": 1, "mythos": 1}, caps={"tiers": 2.5})
    runner = make_runner(cfg, "tiers")
    report = runner.run()
    assert report.stop == "cap" and runner.client.calls == []


def test_tiers_seeds_must_not_overlap_another_real_phase(tmp_path):
    lists = {"dev": [990000], "pilot": [1, 2, 3], "tiers": [3, 4, 5]}
    cfg = make_config(tmp_path, pairs={"fable": 1}, seed_lists=lists)
    with pytest.raises(plan.RunnerError, match="both the tiers and pilot"):
        make_runner(cfg, "tiers", tiers=["fable"]).run()


def test_the_tiers_phase_refuses_dev_seeds(tmp_path):
    cfg = make_config(tmp_path, pairs={"fable": 1}, seed_lists={"dev": [990000], "tiers": [990100, 1]})
    with pytest.raises(plan.RunnerError, match="refuses dev seeds"):
        make_runner(cfg, "tiers", tiers=["fable"]).run()


# ---------------------------------------------------------------- the reserve phase
def test_the_reserve_phase_keeps_its_seed_list_but_has_cap_zero_and_runs_nothing(tmp_path):
    cfg = make_config(tmp_path)
    assert cfg.caps_usd["reserve"] == 0 and cfg.phases["reserve"].seed_file.exists()
    real = load_config()
    assert real.caps_usd["reserve"] == 0 and real.phases["reserve"].seed_file.name == "reserve.txt"
    with pytest.raises(plan.RunnerError, match="plans no pairs"):
        make_runner(make_config(tmp_path, pairs={"haiku": 0, "sonnet": 0, "opus": 0}), "reserve").run()
    # Even if someone planned pairs for it, a cap of 0 refuses every episode before a call is made.
    planned = make_runner(make_config(tmp_path, pairs={"haiku": 1}), "reserve", tiers=["haiku"])
    report = planned.run()
    assert report.stop == "cap" and planned.client.calls == []


# ---------------------------------------------------------------- Mythos is one config value
def test_the_mythos_model_id_is_one_config_value_and_a_switch_needs_only_that_and_a_price(tmp_path):
    cfg = make_config(tmp_path, pairs={"mythos": 1})
    raw = json.loads(cfg.source.read_text(encoding="utf-8"))
    raw["models"]["mythos"] = "claude-mythos-5-1"
    switched = tmp_path / "switched.json"
    switched.write_text(json.dumps(raw), encoding="utf-8")
    cfg2 = load_config(switched)
    # Without a price for the new id the runner refuses to start, naming the model.
    with pytest.raises(PriceError, match="claude-mythos-5-1"):
        make_runner(cfg2, "tiers", tiers=["mythos"]).run()
    # With one, that single value is all that changed.
    prices = json.loads(PRICE_FILE.read_text(encoding="utf-8"))
    prices["models"]["claude-mythos-5-1"] = prices["models"]["claude-mythos-5-2"]
    pf = tmp_path / "prices.json"
    pf.write_text(json.dumps(prices), encoding="utf-8")
    raw["price_file"] = str(pf)
    switched.write_text(json.dumps(raw), encoding="utf-8")
    cfg3 = load_config(switched)
    make_runner(cfg3, "tiers", tiers=["mythos"], script=stay_script()).run()
    header, _, _ = read_log(episodes(cfg3)[0]["log_path"])
    assert header["model"] == "claude-mythos-5-1"


def test_a_price_for_an_unplanned_tier_is_not_needed(tmp_path):
    prices = json.loads(PRICE_FILE.read_text(encoding="utf-8"))
    for m in ("claude-fable-5-2", "claude-mythos-5-2"):
        del prices["models"][m]
    pf = tmp_path / "prices.json"
    pf.write_text(json.dumps(prices), encoding="utf-8")
    cfg = make_config(tmp_path, price_file=pf, pairs={"haiku": 1})
    assert make_runner(cfg, tiers=None, script=stay_script()).run().stop is None  # dev, default tiers
