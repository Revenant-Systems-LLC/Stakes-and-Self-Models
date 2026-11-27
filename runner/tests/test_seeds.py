"""The real seed lists and the real config.json. These read the files in the repository, not test copies."""

import importlib.util
import json
from pathlib import Path

import pytest

from runner import plan
from runner.config import DEV_SEEDS, REPO_ROOT, load_config
from runner.ledger import PriceTable

SEEDS = REPO_ROOT / "runner" / "seeds"
LISTS = {"pilot": 40, "confirmatory": 1300, "reserve": 200, "tiers": 150}   # the least each list may hold


def _generator():
    spec = importlib.util.spec_from_file_location("make_seeds", SEEDS / "make_seeds.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ints(name):
    lines = (SEEDS / f"{name}.txt").read_text(encoding="utf-8").splitlines()
    assert all(l.strip().lstrip("-").isdigit() for l in lines), f"{name}.txt must be one integer per line, nothing else"
    return [int(l) for l in lines]


@pytest.mark.parametrize("name,least", LISTS.items())
def test_each_list_has_enough_seeds(name, least):
    assert len(_ints(name)) >= least


def test_the_sizes_the_job_asked_for_exactly():
    assert {n: len(_ints(n)) for n in LISTS} == {"pilot": 40, "confirmatory": 1300, "reserve": 200, "tiers": 150}


def test_no_seed_repeats_within_or_across_files_and_none_is_a_dev_seed():
    seen: dict[int, str] = {}
    dev = set(_ints("dev"))
    for name in ("dev", *LISTS):
        seeds = _ints(name)
        assert len(seeds) == len(set(seeds)), f"{name}.txt repeats a seed"
        for s in seeds:
            assert s not in seen, f"seed {s} is in both {seen[s]}.txt and {name}.txt"
            seen[s] = name
    for name in LISTS:
        assert not dev & set(_ints(name))
        assert not any(s in DEV_SEEDS for s in _ints(name)), "a real seed fell in the dev range the runner refuses"


def test_the_runner_accepts_each_list_for_its_own_phase():
    for name in LISTS:
        seeds = plan.read_seed_list(SEEDS / f"{name}.txt")
        plan.check_phase_seeds(name, seeds)
    plan.check_disjoint("confirmatory", plan.read_seed_list(SEEDS / "confirmatory.txt"),
                        {n: plan.read_seed_list(SEEDS / f"{n}.txt") for n in ("pilot", "reserve", "tiers")})


def test_the_files_are_what_the_generator_makes_and_the_readme_names_its_seed():
    gen = _generator()
    made = gen.generate()
    assert {n: len(v) for n, v in made.items()} == gen.SIZES
    for name, seeds in made.items():
        assert _ints(name) == seeds
    assert (SEEDS / "README.md").read_text(encoding="utf-8").splitlines()[0] == f"Generator seed: {gen.GENERATOR_SEED}"
    assert gen.generate() == made                     # deterministic
    assert gen.generate(gen.GENERATOR_SEED + 1) != made   # and the seed is what decides it


def test_the_generator_check_command_passes(capsys):
    assert _generator().main(["--check"]) == 0
    assert "match" in capsys.readouterr().out


def test_the_real_config_has_the_tiers_phase_and_the_new_caps():
    cfg = load_config()
    assert cfg.caps_usd["confirmatory"] == 650 and cfg.caps_usd["reserve"] == 0 and cfg.caps_usd["tiers"] == 150
    assert cfg.caps_usd["pilot"] == 100 and cfg.caps_usd["dev"] == 10
    assert cfg.models["fable"] == "claude-fable-5-2" and cfg.models["mythos"] == "claude-mythos-5-2"
    assert cfg.priors_usd["fable"] == 1.30 and cfg.priors_usd["mythos"] == 1.30
    tiers = cfg.phases["tiers"]
    assert tiers.pairs_per_tier == {"haiku": 0, "sonnet": 0, "opus": 0, "fable": 30, "mythos": 30}
    assert tiers.order == "alternate" and tiers.seed_file == SEEDS / "tiers.txt"
    reserve = cfg.phases["reserve"]
    assert reserve.seed_file == SEEDS / "reserve.txt" and sum(reserve.pairs_per_tier.values()) == 0  # list kept, no paid reserve
    assert cfg.phases["confirmatory"].order == "shuffled"
    assert cfg.phases["confirmatory"].pairs_per_tier == {"haiku": 400, "sonnet": 400, "opus": 250, "fable": 0, "mythos": 0}


def test_every_planned_tier_in_the_real_config_has_enough_seeds_and_a_price():
    cfg = load_config()
    prices = PriceTable.load(cfg.price_file)
    for name, ph in cfg.phases.items():
        if name == "dev":
            continue
        need = max(ph.pairs_per_tier.values())
        assert need <= len(plan.read_seed_list(ph.seed_file))
        for tier, n in ph.pairs_per_tier.items():
            if n:
                prices.require(cfg.models[tier])


def test_fable_and_mythos_prices_match_the_job():
    prices = PriceTable.load(load_config().price_file)
    for model in ("claude-fable-5-2", "claude-mythos-5-2"):
        r = prices.rates(model, 1000)
        assert (r["input"], r["cache_write_5m"], r["cache_write_1h"], r["cache_read"], r["output"]) == (8, 10, 16, 0.20, 40)
    raw = json.loads((REPO_ROOT / "runner" / "prices" / "2026-11-26.json").read_text(encoding="utf-8"))
    assert {"claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"} <= set(raw["models"])  # the old prices are untouched
    assert prices.rates("claude-opus-5-5", 1000)["output"] == 20
