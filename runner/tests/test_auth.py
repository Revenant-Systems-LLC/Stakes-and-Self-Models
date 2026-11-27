"""An expired or revoked key (HTTP 401 / authentication_error) stops the run, and the run can be resumed."""

import gzip

import pytest

from runner.claude_critter import AuthFailure, ClaudeCritter, classify_error, is_auth_error
from runner.fake_client import FakeAPIError, FakeClient, error, valid_reply
from runner.ledger import Ledger, PriceTable
from runner.run import AUTH_LINE
from runner.tests.helpers import PRICE_FILE, all_files, make_config, make_runner, manifest, stay_script
from world.log import read_log

FAKE_KEY = "sk-" + "ant-api03-" + "FAKEKEYFORTESTS0123456789abcdef"
EXPECTED_LINE = "The API key was refused (it may have expired). Put a new key in the vault and run the job again."


def episodes(cfg, phase="dev"):
    return [r for r in manifest(cfg, phase) if r["type"] == "episode"]


def fail_on_call(n, step, *, base=None):
    """A script that is valid except for call number n (1-based), which returns step."""
    state = {"i": 0}

    def script(kw):
        state["i"] += 1
        return step if state["i"] == n else (base(kw) if base else valid_reply("stay", 4, "staying"))

    return script


# ---------------------------------------------------------------- recognising the error
def test_the_exact_line_is_what_the_job_asked_for():
    assert AUTH_LINE == EXPECTED_LINE


@pytest.mark.parametrize("exc,expected", [
    (FakeAPIError(401, "x"), True),
    (FakeAPIError(400, "x", error_type="authentication_error"), True),
    (FakeAPIError(500, "x", error_type="authentication_error"), True),
    (FakeAPIError(403, "x", error_type="permission_error"), False),
    (FakeAPIError(429, "x", error_type="rate_limit_error"), False),
    (FakeAPIError(529, "x"), False),
    (RuntimeError("no status"), False),
])
def test_what_counts_as_an_auth_error(exc, expected):
    assert is_auth_error(exc) is expected
    assert (classify_error(exc) == "auth") is expected


def test_the_sdks_bare_inner_body_shape_is_recognised_too():
    exc = FakeAPIError(400, "x")
    exc.body = {"type": "authentication_error", "message": "x"}
    assert is_auth_error(exc)
    exc.body = {"error": "a string, not a dict"}
    assert not is_auth_error(exc)


def test_the_critter_raises_auth_failure_with_no_retry_and_no_text_from_the_error(tmp_path):
    sleeps = []
    ledger = Ledger(tmp_path, "dev", 10, PriceTable.load(PRICE_FILE))
    client = FakeClient([error(401, f"invalid x-api-key: {FAKE_KEY}")])
    critter = ClaudeCritter(client, model="claude-haiku-5-5", system_prompt="s", ledger=ledger, episode_id="e",
                            max_retries=5, sleep=sleeps.append)
    with pytest.raises(AuthFailure) as e:
        critter.reply({"turn": 1}, "t")
    assert len(client.calls) == 1 and sleeps == []  # no retry, no backoff
    assert FAKE_KEY not in str(e.value) and "invalid" not in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__  # the original exception is not chained on
    assert ledger.spend == 0


# ---------------------------------------------------------------- stopping the run
def test_a_401_stops_the_whole_run_at_once_and_is_not_an_exclusion(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 3})
    lines, sleeps = [], []
    runner = make_runner(cfg, tiers=["haiku"], lines=lines, sleeps=sleeps, script=fail_on_call(5, error(401, "bad key")))
    report = runner.run()
    assert report.stop == "auth" and report.exit_code == 5
    assert report.exclusions == [] and report.pairs_done == 0
    assert len(runner.client.calls) == 5 and sleeps == []  # nothing after the refused call, no retry
    assert lines.count(AUTH_LINE) == 1
    m = manifest(cfg)
    assert not [r for r in m if r["type"] == "pair_excluded"]
    assert m[-1]["type"] == "halt" and m[-1]["reason"] == "auth"
    (ep,) = episodes(cfg)
    assert ep["status"] == "incomplete_auth" and ep["condition_code"] == "stakes"


def test_the_open_episodes_log_is_closed_as_incomplete(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    make_runner(cfg, tiers=["haiku"], script=fail_on_call(5, error(401, "bad key"))).run()
    (ep,) = episodes(cfg)
    header, turns, end = read_log(ep["log_path"])
    assert end is not None and end["status"] == "incomplete_auth"
    assert end["turns"] == 4 == len(turns) and end["aborted_turn"] == 5
    assert end["error"] == {"type": "authentication_error", "status_codes": [401]}
    assert end["cost_usd"] == pytest.approx(4 * 0.00015)  # the four answered turns were paid for and are counted


def test_an_authentication_error_body_on_another_status_stops_the_run_too(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    report = make_runner(cfg, tiers=["haiku"], script=fail_on_call(2, error(400, "x", error_type="authentication_error"))).run()
    assert report.stop == "auth" and report.exclusions == []


def test_the_401_stops_the_no_stakes_twin_too(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 2})
    report = make_runner(cfg, tiers=["haiku"], script=fail_on_call(25, error(401, "x"), base=stay_script())).run()
    assert report.stop == "auth"
    assert [(e["condition_code"], e["status"]) for e in episodes(cfg)] == [("stakes", "done"), ("no_stakes", "incomplete_auth")]


def test_the_key_never_reaches_any_line_log_manifest_or_ledger(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    lines = []
    report = make_runner(cfg, tiers=["haiku"], lines=lines,
                         script=fail_on_call(3, error(401, f"invalid x-api-key: {FAKE_KEY}"))).run()
    assert report.stop == "auth"
    seen = "\n".join(lines) + capsys.readouterr().out + capsys.readouterr().err
    for f in all_files(cfg.runs_dir):
        raw = f.read_bytes()
        seen += (gzip.decompress(raw) if f.suffix == ".gz" else raw).decode("utf-8", errors="replace")
    assert "FAKEKEYFORTESTS" not in seen and "sk-ant" not in seen and "invalid x-api-key" not in seen


# ---------------------------------------------------------------- resuming
def test_a_rerun_skips_finished_episodes_and_redoes_the_incomplete_one_on_the_same_seed(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 2})
    first = make_runner(cfg, tiers=["haiku"], script=fail_on_call(25, error(401, "x"), base=stay_script()))
    assert first.run().stop == "auth"  # the first pair: stakes done (20 calls), its no-stakes twin refused on its 5th call
    seed0 = episodes(cfg)[0]["seed"]   # the pair order is shuffled, so whichever of the two seeds came first
    seed1 = ({990000, 990001} - {seed0}).pop()
    stopped_log = next(e for e in episodes(cfg) if e["status"] == "incomplete_auth")["log_path"]
    before = read_log(stopped_log)

    second = make_runner(cfg, tiers=["haiku"], script=stay_script())
    report = second.run()
    assert report.stop is None and report.pairs_done == 2 and report.episodes_run == 3
    assert len(second.client.calls) == 20 + 40  # the redo (20 turns, ending where its stakes twin ended) + all of pair 2

    eps = episodes(cfg)
    assert [(e["seed"], e["condition_code"], e["status"]) for e in eps] == [
        (seed0, "stakes", "done"), (seed0, "no_stakes", "incomplete_auth"),   # the first run
        (seed0, "no_stakes", "done"),                                          # the redo, same seed
        (seed1, "stakes", "done"), (seed1, "no_stakes", "done"),
    ]
    redo = eps[2]
    assert redo["log_path"] != stopped_log and redo["log_path"].endswith(".r1.jsonl.gz")
    assert redo["episode_id"] == f"dev:haiku:{seed0}:no_stakes:r1" != eps[1]["episode_id"]
    h2, t2, e2 = read_log(redo["log_path"])
    assert h2["world_seed"] == seed0 and h2["attempt"] == 1 and e2["status"] == "done"
    assert e2["turns"] == redo["turns"] == eps[0]["turns"] == 20 == len(t2)  # ends on its stakes twin's last turn
    assert read_log(stopped_log) == before                                    # the first log was left exactly as it was
    assert not [r for r in manifest(cfg) if r["type"] == "pair_excluded"]

    third = make_runner(cfg, tiers=["haiku"], script=stay_script())
    again = third.run()
    assert again.pairs_done == 2 and again.episodes_run == 0 and third.client.calls == []

    led = Ledger(cfg.runs_dir, "dev", 10, PriceTable.load(PRICE_FILE))
    assert led.spend == pytest.approx((20 + 4 + 20 + 40) * 0.00015)  # every answered call is on the books, once


def test_a_refused_stakes_twin_is_replayed_then_its_twin_runs(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    make_runner(cfg, tiers=["haiku"], script=fail_on_call(3, error(401, "x"), base=stay_script())).run()
    again = make_runner(cfg, tiers=["haiku"], script=stay_script())
    report = again.run()
    assert report.pairs_done == 1 and report.stop is None
    assert [(e["seed"], e["condition_code"], e["status"]) for e in episodes(cfg)] == [
        (990000, "stakes", "incomplete_auth"), (990000, "stakes", "done"), (990000, "no_stakes", "done")]
    assert all(e["seed"] == 990000 for e in episodes(cfg))  # never moved to a replacement seed


def test_resume_works_in_a_blinded_phase_too(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    key = tmp_path / "key" / "blinding_key.json"
    make_runner(cfg, "confirmatory", tiers=["haiku"], key_path=key, script=fail_on_call(2, error(401, "x"))).run()
    report = make_runner(cfg, "confirmatory", tiers=["haiku"], key_path=key).run()
    assert report.stop is None and report.pairs_done == 1
    names = [p.name for p in all_files(cfg.runs_dir / "confirmatory" / "logs")]
    assert len(names) == 3 and not any("stakes" in n for n in names)
