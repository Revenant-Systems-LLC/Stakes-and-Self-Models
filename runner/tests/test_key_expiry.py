"""The key-expiry guard (--key-expires), with a fake client and a fake clock."""

from datetime import datetime, timedelta, timezone

import pytest

from runner.fake_client import valid_reply
from runner.plan import RunnerError
from runner.run import Runner, main, parse_key_expires, require_key_expires
from runner.tests.helpers import FakeClock, T0, make_config, make_runner, manifest

CST = timezone(timedelta(hours=-6))


def ticking(clock, minutes=1.0):
    """Every API call takes `minutes` on the fake clock. A pair of a critter that never eats is 40 calls (two twins of 20 turns)."""
    def script(kw):
        clock.advance(minutes=minutes)
        return valid_reply("stay", 4, "staying")
    return script


def test_parse_key_expires():
    assert parse_key_expires("2026-12-03T21:35-06:00") == datetime(2026, 12, 3, 21, 35, tzinfo=CST)
    assert parse_key_expires(" 2026-12-04T03:35:00+00:00 ") == datetime(2026, 12, 3, 21, 35, tzinfo=CST)
    for bad in ("2026-12-03T21:35", "2026-12-03", "tomorrow", "", "2026-13-40T00:00+00:00"):
        with pytest.raises(RunnerError, match="ISO 8601 time with an offset"):
            parse_key_expires(bad)


# ---------------------------------------------------------------- required for every phase but dev
@pytest.mark.parametrize("phase", ["pilot", "confirmatory", "reserve", "tiers"])
def test_every_phase_but_dev_refuses_to_start_without_key_expires(tmp_path, phase):
    cfg = make_config(tmp_path)
    runner = make_runner(cfg, phase, key_expires=None)
    with pytest.raises(RunnerError, match=rf"--key-expires is required for the {phase} phase"):
        runner.run()
    assert runner.client.calls == [] and not cfg.runs_dir.exists()  # nothing read, nothing written


def test_dev_runs_without_it_and_with_it(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    assert make_runner(cfg, tiers=["haiku"]).run().stop is None
    other = tmp_path / "with_expiry"
    other.mkdir()
    clock = FakeClock()
    assert make_runner(make_config(other, pairs={"haiku": 1}), tiers=["haiku"], clock=clock,
                       key_expires=clock.now + timedelta(days=7)).run().stop is None


@pytest.mark.parametrize("phase", ["pilot", "confirmatory", "reserve", "tiers"])
def test_the_command_line_refuses_without_it_before_touching_anything(tmp_path, capsys, phase):
    cfg = make_config(tmp_path, pairs={"fable": 1, "mythos": 1})
    assert main(["--phase", phase, "--client", "fake", "--config", str(cfg.source), "--no-progress"]) == 2
    err = capsys.readouterr().err
    assert "--key-expires is required" in err and phase in err
    assert not cfg.runs_dir.exists()


def test_the_command_line_rejects_a_time_with_no_offset(tmp_path, capsys):
    cfg = make_config(tmp_path)
    assert main(["--phase", "pilot", "--config", str(cfg.source), "--key-expires", "2026-12-03T21:35"]) == 2
    assert "with an offset" in capsys.readouterr().err


def test_the_command_line_runs_the_tiers_phase_with_it(tmp_path, capsys):
    cfg = make_config(tmp_path, pairs={"fable": 1, "mythos": 1})
    assert main(["--phase", "tiers", "--config", str(cfg.source), "--no-progress", "--key-expires", "2099-01-01T00:00+00:00"]) == 0
    out = capsys.readouterr().out
    assert "hours left" in out and "finished: 2 pairs" in out


def test_require_key_expires_unit():
    require_key_expires("dev", None)
    require_key_expires("pilot", T0)
    with pytest.raises(RunnerError):
        require_key_expires("confirmatory", None)


# ---------------------------------------------------------------- the start line
def test_the_start_prints_the_hours_the_key_has_left(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    lines = []
    clock = FakeClock()
    make_runner(cfg, tiers=["haiku"], lines=lines, clock=clock, key_expires=clock.now + timedelta(days=7, hours=2, minutes=30)).run()
    assert lines[0] == "The key has 170.5 hours left (it expires at 2026-12-08T14:30+00:00)."


def test_an_expiry_already_past_stops_before_the_first_pair(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 2})
    lines = []
    clock = FakeClock()
    runner = make_runner(cfg, tiers=["haiku"], lines=lines, clock=clock, key_expires=clock.now - timedelta(hours=3))
    report = runner.run()
    assert lines[0] == "The key expired 3.0 hours ago (at 2026-12-01T09:00+00:00)."
    assert report.stop == "key_expiry" and report.pairs_done == 0 and runner.client.calls == []


# ---------------------------------------------------------------- the guard
def test_the_run_stops_before_the_pair_that_would_straddle_the_expiry(tmp_path):
    # A pair takes 40 minutes (40 calls of 1 minute). Before any pair finishes the estimate is 30 minutes.
    # Expiry 16:00 UTC (written as 10:00-06:00), start 12:00:
    #   before pair 1: 12:00 + 2 x 30 min + 1 h = 13:00, fine (pair 1 ends 12:40, mean 40 min)
    #   before pair 2: 12:40 + 80 min + 1 h = 15:00, fine (ends 13:20)
    #   before pair 3: 13:20 + 80 min + 1 h = 15:40, fine (ends 14:00)
    #   before pair 4: 14:00 + 80 min + 1 h = 16:20 > 16:00, stop.
    cfg = make_config(tmp_path, pairs={"haiku": 6})
    clock, lines = FakeClock(), []
    expires = datetime(2026, 12, 1, 10, 0, tzinfo=CST)
    runner = make_runner(cfg, tiers=["haiku"], script=None, lines=lines, clock=clock, key_expires=expires)
    runner.client.script = ticking(clock)
    report = runner.run()
    assert report.stop == "key_expiry" and report.exit_code == 5 and report.pairs_done == 3
    assert len(runner.client.calls) == 3 * 40  # no pair was started after the stop
    msg = ("The key expires at 2026-12-01T10:00-06:00. Stopping before the next pair so no batch straddles it. "
           "Put a new key in the vault and rerun with its new expiry.")
    assert lines.count(msg) == 1
    assert manifest(cfg)[-1] == {**manifest(cfg)[-1], "type": "halt", "reason": "key_expiry", "detail": msg}
    assert not [r for r in manifest(cfg) if r["type"] == "pair_excluded"]  # a clean stop, not an exclusion
    assert clock.now == T0 + timedelta(hours=2)


def test_the_edge_is_inclusive_with_the_thirty_minute_guess_before_any_pair_finishes(tmp_path):
    # Now + 2 x 30 min + 1 h = 2 h exactly. An expiry exactly then lets the pair start; one second earlier does not.
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    clock = FakeClock()
    allowed = make_runner(cfg, tiers=["haiku"], clock=clock, key_expires=clock.now + timedelta(hours=2))
    assert allowed.run().stop is None and len(allowed.client.calls) == 40


def test_one_second_short_of_the_margin_does_not_start(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    clock = FakeClock()
    runner = make_runner(cfg, tiers=["haiku"], clock=clock, key_expires=clock.now + timedelta(hours=2) - timedelta(seconds=1))
    assert runner.run().stop == "key_expiry" and runner.client.calls == []


def test_the_estimate_is_the_mean_of_pairs_played_in_full_in_this_run(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 2})
    clock = FakeClock()
    first = make_runner(cfg, tiers=["haiku"], clock=clock, key_expires=clock.now + timedelta(days=7))
    first.client.script = ticking(clock, minutes=1)
    first.run()
    assert first._pair_durations == [timedelta(minutes=40), timedelta(minutes=40)]
    assert first._pair_estimate() == timedelta(minutes=40)
    # A rerun that only skips finished pairs plays nothing, so it learns nothing and keeps the 30 minute guess.
    again = make_runner(cfg, tiers=["haiku"], clock=clock, key_expires=clock.now + timedelta(days=7))
    assert again.run().pairs_done == 2
    assert again._pair_durations == [] and again._pair_estimate() == timedelta(minutes=30)


def test_the_guard_also_covers_a_replacement_pair_after_an_exclusion(tmp_path):
    from runner.fake_client import error
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    clock = FakeClock()
    state = {"n": 0}

    def script(kw):
        state["n"] += 1
        clock.advance(minutes=1)
        return error(400, "x") if state["n"] == 1 else valid_reply("stay", 4, "staying")

    # Pair 1 is excluded on its first call at 12:01. The replacement would need 12:01 + 1 h + 1 h = 14:01.
    runner = make_runner(cfg, tiers=["haiku"], clock=clock, key_expires=T0 + timedelta(hours=2, minutes=1) - timedelta(seconds=1),
                         script=script)
    report = runner.run()
    assert report.stop == "key_expiry" and report.pairs_done == 0 and len(report.exclusions) == 1
    assert state["n"] == 1


def test_without_an_expiry_in_dev_the_guard_is_off_however_late_it_is(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    clock = FakeClock()
    runner = make_runner(cfg, tiers=["haiku"], clock=clock, key_expires=None)
    runner.client.script = ticking(clock, minutes=600)
    assert runner.run().stop is None
