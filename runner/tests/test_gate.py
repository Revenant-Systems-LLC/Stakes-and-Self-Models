import gzip
import sys

import pytest

import runner.gate as gate
from runner.fake_client import FakeAPIError, FakeClient, valid_reply, error
from runner.run import main
from runner.tests.helpers import all_files, make_config, make_runner

# Built from pieces so no key-shaped literal sits in the source for a secret scanner to trip on.
FAKE_KEY = "sk-" + "ant-api03-" + "FAKEKEYFORTESTS0123456789abcdef"


@pytest.mark.parametrize("value", [None, "", "Yes", "YES", "true", "1", "yes ", " yes", "y"])
def test_no_real_client_without_exactly_yes(monkeypatch, value):
    if value is not None:
        monkeypatch.setenv("STAKES_ALLOW_API", value)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)  # even with a key present
    assert not gate.api_allowed()
    with pytest.raises(gate.ApiNotAllowed):  # the autouse tripwire would raise AssertionError if a client were built
        gate.make_claude_client()
    assert "fake client only" in gate.mode_line()


def test_the_real_client_is_built_only_when_the_gate_is_open_and_never_with_our_copy_of_the_key(monkeypatch):
    import anthropic

    built = []

    class Sentinel:
        def __init__(self, *a, **kw):
            built.append((a, kw))

    monkeypatch.setattr(anthropic, "Anthropic", Sentinel)
    monkeypatch.setenv("STAKES_ALLOW_API", "yes")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    client = gate.make_claude_client()
    assert isinstance(client, Sentinel)
    assert built == [((), {"max_retries": 0})]  # no api_key argument: the SDK reads the process environment itself
    assert "ENABLED" in gate.mode_line()


def test_cli_with_the_claude_client_and_a_closed_gate_exits_nonzero(tmp_path, capsys):
    cfg = make_config(tmp_path)
    code = main(["--phase", "pilot", "--client", "claude", "--config", str(cfg.source), "--no-progress"])
    out = capsys.readouterr()
    assert code == 2 and "fake client only" in out.out and "STAKES_ALLOW_API" in out.err
    assert all_files(cfg.runs_dir) == []


def test_cli_dev_phase_never_runs_on_the_real_client(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("STAKES_ALLOW_API", "yes")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    cfg = make_config(tmp_path)
    assert main(["--phase", "dev", "--client", "claude", "--config", str(cfg.source), "--no-progress"]) == 2
    assert "fake client only" in capsys.readouterr().err
    assert all_files(cfg.runs_dir) == []


def test_preflight_fails_when_the_key_is_missing_before_anything_is_written(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("STAKES_ALLOW_API", "yes")  # gate open, no ANTHROPIC_API_KEY in this process
    cfg = make_config(tmp_path)
    code = main(["--phase", "pilot", "--client", "claude", "--config", str(cfg.source), "--no-progress"])
    err = capsys.readouterr().err
    assert code == 2
    assert "ANTHROPIC_API_KEY is not set" in err and "job watcher" in err and "user or system environment variable" in err
    assert all_files(cfg.runs_dir) == [] and not cfg.runs_dir.exists()  # no ledger, no manifest, no log file


def test_preflight_fails_when_the_key_is_blank(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("STAKES_ALLOW_API", "yes")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    cfg = make_config(tmp_path)
    assert main(["--phase", "pilot", "--client", "claude", "--config", str(cfg.source), "--no-progress"]) == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err
    assert not cfg.runs_dir.exists()


def test_preflight_fails_when_the_anthropic_package_does_not_import(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("STAKES_ALLOW_API", "yes")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setitem(sys.modules, "anthropic", None)  # makes `import anthropic` raise ImportError
    cfg = make_config(tmp_path)
    code = main(["--phase", "pilot", "--client", "claude", "--config", str(cfg.source), "--no-progress"])
    out = capsys.readouterr()
    assert code == 2
    assert "anthropic package does not import" in out.err
    assert FAKE_KEY not in out.out + out.err  # the key is never printed
    assert not cfg.runs_dir.exists()


def test_preflight_reports_both_problems_at_once(monkeypatch):
    monkeypatch.setenv("STAKES_ALLOW_API", "yes")
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(gate.PreflightError) as e:
        gate.preflight()
    assert "ANTHROPIC_API_KEY" in str(e.value) and "anthropic package" in str(e.value)


def test_the_key_never_reaches_a_ledger_log_manifest_or_status_line(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    cfg = make_config(tmp_path, pairs={"haiku": 2})
    calls = {"n": 0}

    def script(kwargs):
        calls["n"] += 1
        if calls["n"] == 3:  # an SDK error that echoes the key back, which must be scrubbed everywhere
            return error(401, f"invalid x-api-key: {FAKE_KEY}")
        return valid_reply("stay")

    lines = []
    report = make_runner(cfg, tiers=["haiku"], script=script, lines=lines).run()
    assert report.exclusions  # the 401 excluded an episode, so its error text was written somewhere
    seen = "\n".join(lines) + capsys.readouterr().out
    for f in all_files(cfg.runs_dir):
        raw = f.read_bytes()
        seen += (gzip.decompress(raw) if f.suffix == ".gz" else raw).decode("utf-8", errors="replace")
    assert FAKE_KEY not in seen and "FAKEKEYFORTESTS" not in seen
    assert "[redacted]" in seen
