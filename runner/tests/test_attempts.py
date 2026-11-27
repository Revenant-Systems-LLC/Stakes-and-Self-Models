"""A voided pilot attempt: the rerun writes to its own folder, skips every seed the voided attempt touched for every
tier, shares the phase's ledger, and never writes into the voided folder."""

import json

import pytest

from runner.config import ConfigError, load_config, phase_dir
from runner.tests.helpers import make_config, make_runner, manifest


def _files(d):
    return sorted((p.relative_to(d), p.stat().st_size) for p in d.rglob("*") if p.is_file())


def test_attempt_two_skips_every_seed_attempt_one_touched_and_leaves_it_alone(tmp_path):
    cfg1 = make_config(tmp_path, pairs={"haiku": 2, "sonnet": 1})
    make_runner(cfg1, "pilot").run()
    first = phase_dir(cfg1.runs_dir, "pilot", 1)
    used = {r["seed"] for r in manifest(cfg1, "pilot") if r["type"] == "episode"}
    assert used == {1000, 1001}
    # an orphan log from a hard stop counts as touched too
    (first / "logs" / "opus").mkdir(parents=True, exist_ok=True)
    (first / "logs" / "opus" / "1007-stakes.jsonl.gz").write_bytes(b"")
    before = _files(first)
    spend1 = json.loads((cfg1.runs_dir / "ledger" / "pilot.jsonl").read_text().splitlines()[-1])

    cfg2 = make_config(tmp_path, pairs={"haiku": 2, "sonnet": 1}, attempts={"pilot": 2})
    lines = []
    r = make_runner(cfg2, "pilot", lines=lines)
    report = r.run()
    assert report.stop is None
    second = phase_dir(cfg2.runs_dir, "pilot", 2)
    assert second.name == "pilot-attempt2"
    recs = [json.loads(x) for x in (second / "manifest.jsonl").read_text().splitlines()]
    voided = {(x["tier"], x["seed"]) for x in recs if x["type"] == "pair_excluded"}
    for tier in ("haiku", "sonnet", "opus", "fable", "mythos"):
        assert {(tier, s) for s in (1000, 1001, 1007)} <= voided
    played = {(x["tier"], x["seed"]) for x in recs if x["type"] == "episode"}
    assert played == {("haiku", 1002), ("haiku", 1003), ("sonnet", 1002), ("opus", 1002)}
    assert _files(first) == before          # the voided attempt is only read
    assert any("attempt 2" in m for m in lines)
    assert r.ledger.spend >= 0 and (cfg2.runs_dir / "ledger" / "pilot.jsonl").exists() and spend1


def test_resuming_attempt_two_does_not_void_twice(tmp_path):
    make_runner(make_config(tmp_path, pairs={"haiku": 1}), "pilot").run()
    cfg2 = make_config(tmp_path, pairs={"haiku": 1}, attempts={"pilot": 2})
    make_runner(cfg2, "pilot").run()
    n = len((phase_dir(cfg2.runs_dir, "pilot", 2) / "manifest.jsonl").read_text().splitlines())
    make_runner(cfg2, "pilot").run()
    assert len((phase_dir(cfg2.runs_dir, "pilot", 2) / "manifest.jsonl").read_text().splitlines()) == n


@pytest.mark.parametrize("phase,value", [("confirmatory", 2), ("tiers", 2), ("pilot", 0), ("pilot", True), ("pilot", "2")])
def test_only_dev_and_pilot_take_a_whole_attempt_number(tmp_path, phase, value):
    with pytest.raises(ConfigError, match="attempt"):
        make_config(tmp_path, attempts={phase: value})


def test_the_repository_config_reruns_the_pilot_as_attempt_two():
    cfg = load_config()
    assert cfg.phases["pilot"].attempt == 2
    assert cfg.phases["pilot"].pairs_per_tier == {"haiku": 5, "sonnet": 3, "opus": 2, "fable": 1, "mythos": 1}
