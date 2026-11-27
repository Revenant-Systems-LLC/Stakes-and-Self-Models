"""The status line that keeps a run's window from looking frozen."""

import re
import time

from runner.fake_client import valid_reply
from runner.run import Heartbeat
from runner.tests.helpers import make_config, make_runner

FIELDS = re.compile(r"heartbeat \d\d:\d\d:\d\d \| phase (\w+) \| model (\S+) \| pair (\d+)/(\d+) \| turn (\d+|-)/(\d+|-) \| "
                    r"spend \$([\d.]+) of \$([\d.]+) cap( \(\d+%\))?$")


class Mono:
    """A fake time.monotonic."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_a_line_prints_every_interval_and_not_before():
    mono, lines = Mono(), []
    hb = Heartbeat(lines.append, 30, mono)
    assert hb.beat() is False and lines == []  # nothing to say yet
    hb.update(phase="tiers", model="claude-fable-5-2", pair=3, pairs=60, turn=12, max_turns=48, spend=4.21, cap=150.0)
    mono.t = 29.9
    assert hb.beat() is False
    mono.t = 30.0
    assert hb.beat() is True and len(lines) == 1
    assert hb.beat() is False                      # just printed
    mono.t = 59.9
    assert hb.beat() is False
    mono.t = 60.0
    assert hb.beat() is True and len(lines) == 2
    m = FIELDS.search(lines[0])
    assert m and m.group(1, 2, 3, 4, 5, 6, 7, 8) == ("tiers", "claude-fable-5-2", "3", "60", "12", "48", "4.21", "150.00")
    assert lines[0].endswith("spend $4.21 of $150.00 cap (3%)")


def test_force_prints_at_once_and_a_zero_cap_has_no_percent():
    mono, lines = Mono(), []
    hb = Heartbeat(lines.append, 30, mono)
    hb.update(phase="reserve", spend=0.0, cap=0.0)
    assert hb.beat(force=True) and lines[0].endswith("spend $0.00 of $0.00 cap")


def test_a_run_prints_a_status_line_at_least_every_30_seconds_of_clock_time(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    mono, lines = Mono(), []

    def script(kw):
        mono.t += 10.0  # every API call takes 10 seconds
        return valid_reply("stay", 4, "staying")

    runner = make_runner(cfg, tiers=["haiku"], script=script, lines=lines, heartbeat_seconds=30, heartbeat_clock=mono)
    runner.run()
    beats = [l for l in lines if l.startswith("heartbeat")]
    calls = len(runner.client.calls)
    assert calls == 40 and len(beats) >= calls * 10 // 30 - 1   # 400 s of run, so about 13 lines
    for l in beats:
        m = FIELDS.search(l)
        assert m, l
        assert m.group(1, 2, 3, 4, 8) == ("dev", "claude-haiku-5-5", "1", "1", "10.00")
    assert any("turn 0/" in l or re.search(r"turn \d+/48", l) for l in beats)
    spends = [float(FIELDS.search(l).group(7)) for l in beats]
    assert spends == sorted(spends)               # spend only goes up through the run
    # Between two lines at most 3 or 4 API calls (30 s at 10 s each) go by, never a long silent stretch.
    idx = [i for i, l in enumerate(lines) if l.startswith("heartbeat")]
    assert all(b - a <= 6 for a, b in zip(idx, idx[1:]))


def test_the_background_thread_prints_while_one_call_is_slow_and_stops_after_the_run(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    lines = []

    def script(kw):
        time.sleep(0.03)  # a slow API call: the main thread is stuck in it, the thread must still speak
        return valid_reply("stay", 4, "staying")

    runner = make_runner(cfg, tiers=["haiku"], script=script, lines=lines, limit_pairs=1,
                         heartbeat_seconds=0.1, heartbeat_thread=True)
    runner.run()
    beats = [l for l in lines if l.startswith("heartbeat")]
    assert len(beats) >= 3 and all(FIELDS.search(l) for l in beats)
    assert runner.heartbeat._thread is not None and not runner.heartbeat._thread.is_alive()
    n = len(lines)
    time.sleep(0.3)
    assert len(lines) == n                          # nothing printed after the run ended
