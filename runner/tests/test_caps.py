import json

import pytest

from runner import run as run_mod
from runner.config import REPO_ROOT, ConfigError, load_config
from runner.run import parse_args
from runner.tests.helpers import all_files, make_config, make_runner, manifest, read_gz_lines, stay_script


@pytest.mark.parametrize("flag", ["--cap", "--cap-usd", "--caps", "--budget", "--runs-dir", "--ledger"])
def test_no_command_line_option_changes_a_cap_or_the_ledger(flag):
    with pytest.raises(SystemExit):
        parse_args(["--phase", "pilot", flag, "9999"])


def test_a_config_cannot_raise_a_cap_above_the_preregistered_one(tmp_path):
    for phase, too_big in (("pilot", 101), ("confirmatory", 751), ("reserve", 151)):
        with pytest.raises(ConfigError, match="cannot be raised"):
            make_config(tmp_path, caps={phase: too_big})
    make_config(tmp_path, caps={"pilot": 100, "confirmatory": 750, "reserve": 150})  # the plan itself is fine
    make_config(tmp_path, caps={"pilot": 5})  # lowering is fine


def test_config_rejects_a_runs_dir_inside_the_repo_and_unknown_keys(tmp_path):
    cfg = make_config(tmp_path)
    raw = json.loads(cfg.source.read_text(encoding="utf-8"))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**raw, "runs_dir": str(REPO_ROOT / "runs")}), encoding="utf-8")
    with pytest.raises(ConfigError, match="outside the repository"):
        load_config(bad)
    bad.write_text(json.dumps({**raw, "cap": 5}), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown config keys"):
        load_config(bad)


def test_pre_episode_refusal_uses_the_prior_before_any_call(tmp_path):
    # Dev cap $0.50. Sonnet's prior is $0.45, so 2 x 0.45 = 0.90 would pass the cap: refuse, spend nothing.
    cfg = make_config(tmp_path, caps={"dev": 0.5}, pairs={"sonnet": 1})
    lines = []
    runner = make_runner(cfg, tiers=["sonnet"], lines=lines)
    report = runner.run()
    assert report.stop == "cap" and report.exit_code == 3
    assert runner.client.calls == []
    assert not (cfg.runs_dir / "dev" / "logs").exists()  # no episode log was opened
    assert not (cfg.runs_dir / "ledger" / "dev.jsonl").exists()  # nothing was spent
    assert any("will not start" in l and "prior" in l for l in lines)
    assert manifest(cfg)[-1]["type"] == "halt" and manifest(cfg)[-1]["reason"] == "cap"


def test_pre_episode_refusal_uses_the_running_mean_once_a_tier_has_finished_an_episode(tmp_path):
    # Each fake response costs 1,000 x 0.10 + 100 x 0.50 = $0.00015. A Haiku stakes episode that faints on turn 20 is
    # 20 calls = $0.003, so the running mean is $0.003 and the no-stakes twin (20 turns) is allowed. The prior is $0.03.
    # The cap is set so that spend + 2 x mean passes it for the NEXT pair but the first episode (prior 0.03 -> 0.06) fits.
    cfg = make_config(tmp_path, caps={"dev": 0.07}, pairs={"haiku": 3})
    runner = make_runner(cfg, tiers=["haiku"], script=stay_script())
    report = runner.run()
    # Pair 1: stakes starts on the prior (0 + 0.06 <= 0.07), costs 0.003. No-stakes: 0.003 + 2 x 0.003 = 0.009, fine.
    # Everything stays far under 0.07 on the running mean, so all three pairs run: the mean, not the prior, governs.
    assert report.stop is None and report.pairs_done == 3
    first = manifest(cfg)[0]
    assert first["status"] == "done" and first["cost_usd"] == pytest.approx(20 * 0.00015)


def test_running_mean_can_refuse_what_the_prior_allowed(tmp_path):
    cfg = make_config(tmp_path, caps={"dev": 0.0095}, priors={"haiku": 0.001}, pairs={"haiku": 3})
    runner = make_runner(cfg, tiers=["haiku"], script=stay_script())
    lines = []
    runner.say = lines.append
    report = runner.run()
    # Stakes twin: starts on the prior (0 + 0.002 <= 0.0095), 20 calls = 0.003. No-stakes twin: 0.003 + 2 x 0.003 = 0.009 fits.
    # Next pair's stakes twin: spend 0.006 + 2 x 0.003 = 0.012 > 0.0095, refused on the running mean.
    assert report.stop == "cap" and report.pairs_done == 1
    assert any("running mean" in l and "will not start" in l for l in lines)
    assert len([r for r in manifest(cfg) if r["type"] == "episode"]) == 2


def test_mid_episode_stop_when_a_response_crosses_the_cap(tmp_path):
    # Each response costs $0.00015; a $0.001 cap is passed by the 7th response (0.00105). The prior is set low
    # so the episode is allowed to start.
    cfg = make_config(tmp_path, caps={"dev": 0.001}, priors={"haiku": 0.0001}, pairs={"haiku": 2})
    runner = make_runner(cfg, tiers=["haiku"], script=stay_script())
    report = runner.run()
    assert report.stop == "cap" and report.exit_code == 3
    assert len(runner.client.calls) == 7  # nothing ran after the crossing response

    (ep,) = [r for r in manifest(cfg) if r["type"] == "episode"]
    assert ep["status"] == "aborted_cap"
    header, turns, end = _read(ep["log_path"])
    assert end["status"] == "aborted_cap" and end["turns"] == 6 == len(turns)
    assert end["aborted_turn"] == 7 and end["cap"]["cap"] == 0.001
    assert end["aborted_calls"][0]["cost_usd"] == pytest.approx(0.00015)
    assert end["cost_usd"] == pytest.approx(7 * 0.00015)  # the crossing response is paid for and counted

    from runner.ledger import Ledger, PriceTable
    led = Ledger(cfg.runs_dir, "dev", 0.001, PriceTable.load(cfg.price_file))
    assert led.spend == pytest.approx(7 * 0.00015) and led.spend > 0.001


def test_a_restart_cannot_forget_the_spend_and_runs_nothing_more(tmp_path):
    cfg = make_config(tmp_path, caps={"dev": 0.001}, priors={"haiku": 0.0001}, pairs={"haiku": 2})
    make_runner(cfg, tiers=["haiku"], script=stay_script()).run()
    again = make_runner(cfg, tiers=["haiku"], script=stay_script())
    report = again.run()
    assert report.stop == "cap" and again.client.calls == []


def _read(path):
    from world.log import read_log
    return read_log(path)
