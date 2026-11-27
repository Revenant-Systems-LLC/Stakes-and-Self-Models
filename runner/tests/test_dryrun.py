"""runner/dryrun.py: the scripted dry run plays through the runner's play path, touches nothing real, and its logs pass
runner/check_logs.py. The faulted copy it makes is caught by the checker. No model is called (the autouse tripwire in
conftest.py fails any test that builds an Anthropic client)."""

import json
from pathlib import Path

import pytest

from runner import check_logs, dryrun
from runner.config import REPO_ROOT, load_config
from runner.plan import RunnerError
from runner.tests.helpers import all_files
from world import blinding
from world.log import read_log

QUESTION = (REPO_ROOT / "prompts" / "checkin_question.txt").read_text(encoding="utf-8").strip()


@pytest.fixture
def played(tmp_path):
    out = tmp_path / "dry"
    records = dryrun.run_dryrun(out, pairs=2, blinded_pairs=1, progress=False, heartbeat_thread=False, say=lambda m: None)
    return out, records


def check(folder, **kw):
    return check_logs.check_directory(folder, question=QUESTION, prereg_text=(REPO_ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8"), **kw)


def test_plays_the_planned_groups_and_every_log_passes_the_checker(played):
    out, records = played
    assert len(records) == 2 * (2 + 2 + 1 + 1) == 12
    logs = out / "logs"
    assert sorted(p.name for p in logs.iterdir()) == ["blinded-scripted-greedy", "blinded-scripted-random",
                                                      "scripted-greedy", "scripted-random"]
    for folder in logs.iterdir():
        r = check(folder, blinded="yes" if folder.name.startswith("blinded-") else "no")
        assert r.failures == [] and r.pairs == len(list(folder.glob("*.jsonl.gz"))) // 2, (folder, r.failures)


def test_uses_dev_seeds_only_and_the_plain_and_blinded_seeds_differ(played):
    out, records = played
    dev = [int(x) for x in (REPO_ROOT / "runner" / "seeds" / "dev.txt").read_text().split()]
    plain = {r["seed"] for r in records if not r["group"].startswith("blinded-")}
    blinded = {r["seed"] for r in records if r["group"].startswith("blinded-")}
    assert plain == set(dev[:2]) and blinded == {dev[2]}
    assert all(990000 <= r["seed"] < 990200 for r in records)


def test_the_blinded_logs_carry_codes_from_a_scratch_key_inside_the_output_folder(played):
    out, records = played
    key = json.loads((out / "blinding_key.json").read_text())
    assert set(key) == {"stakes", "no_stakes"}
    codes = {read_log(p)[0]["condition_code"] for p in (out / "logs").glob("blinded-*/*.jsonl.gz")}
    assert codes == set(key.values())
    assert not any("stakes" in p.name for p in (out / "logs").glob("blinded-*/*"))
    assert blinding.DEFAULT_KEY_PATH.resolve() != (out / "blinding_key.json").resolve()


def test_the_twin_is_held_to_its_stakes_twins_last_turn_and_logs_carry_the_question(played):
    out, records = played
    for g in {r["group"] for r in records}:
        by_seed = {}
        for r in (r for r in records if r["group"] == g):
            by_seed.setdefault(r["seed"], {})[r["condition"]] = r
        assert all(p["stakes"]["turns"] == p["no_stakes"]["turns"] for p in by_seed.values())
    header, turns, end = read_log(records[0]["path"])
    assert [t["checkin_question"] for t in turns if t["checkin"]] == [QUESTION] * 4
    assert header["phase"] == "dryrun" and header["model"] == "scripted-greedy"


def test_writes_only_logs_and_the_scratch_key_never_a_ledger_or_manifest(played):
    out, _ = played
    names = {p.relative_to(out).parts[0] for p in all_files(out)}
    assert names == {"logs", "blinding_key.json"}
    assert not (out / "manifest.jsonl").exists() and not any("ledger" in p.name for p in all_files(out))


def test_refuses_to_run_into_a_folder_that_already_holds_logs(played):
    out, _ = played
    before = {p: p.stat().st_mtime_ns for p in all_files(out)}
    with pytest.raises(RunnerError, match="already holds logs"):
        dryrun.run_dryrun(out, pairs=2, blinded_pairs=1, progress=False, heartbeat_thread=False, say=lambda m: None)
    assert before == {p: p.stat().st_mtime_ns for p in all_files(out)}


def test_refuses_an_output_folder_inside_the_repo_or_in_a_real_phase(tmp_path):
    cfg = load_config()
    with pytest.raises(RunnerError, match="outside the repository"):
        dryrun.check_out_dir(REPO_ROOT / "dry", cfg)
    for phase in ("pilot", "confirmatory"):
        with pytest.raises(RunnerError, match="real phase"):
            dryrun.check_out_dir(cfg.runs_dir / phase / "logs", cfg)
    assert dryrun.check_out_dir(cfg.runs_dir / "dryrun", cfg) == (cfg.runs_dir / "dryrun").resolve()


def test_never_uses_the_real_blinding_key(tmp_path):
    with pytest.raises(RunnerError, match="real blinding key"):
        dryrun.scratch_key_path(blinding.DEFAULT_KEY_PATH.parent)   # an out folder that would put the key at the real path


def test_pair_counts_must_fit_the_dev_seed_list(tmp_path):
    with pytest.raises(RunnerError, match="need"):
        dryrun.plan_groups(list(range(990000, 990005)), 4, 2)


def test_faint_rate_counts_stakes_episodes_of_one_agent(played):
    _, records = played
    fainted, n = dryrun.faint_rate(records, "greedy")
    assert n == 2 and 0 <= fainted <= n
    fainted, n = dryrun.faint_rate(records, "random")
    assert n == 2 and fainted == 2   # the random critter starves
    assert dryrun.faint_rate(records, "greedy", blinded=True)[1] == 1
    assert any(line.startswith("greedy:") for line in dryrun.summary_lines(records))


def test_the_faulted_copy_is_caught_for_both_faults_and_the_original_is_untouched(played, tmp_path):
    out, records = played
    src = next(Path(r["path"]) for r in records if r["agent"] == "greedy" and r["condition"] == "stakes" and r["turns"] == 48)
    before = src.read_bytes()
    info = dryrun.inject_faults(src, tmp_path / "faulted" / src.name)
    assert src.read_bytes() == before
    r = check_logs.check_directory(tmp_path / "faulted", question=QUESTION)
    assert not r.ok
    assert any("is missing" in f and f"turn {info['check_in_removed_at_turn']}" in f for f in r.failures)
    assert any(f"check-in answer of turn {info['answer_from_turn']}" in f and "appears in the diary" in f for f in r.failures)
    with pytest.raises(RunnerError, match="refusing to overwrite"):
        dryrun.inject_faults(src, tmp_path / "faulted" / src.name)


def test_a_log_that_cannot_be_faulted_is_refused(tmp_path, played):
    out, records = played
    short = next(Path(r["path"]) for r in records if r["agent"] == "random" and r["condition"] == "stakes")
    with pytest.raises(RunnerError):   # fainted before a second check-in
        dryrun.inject_faults(short, tmp_path / "x.jsonl.gz")


def test_command_line(tmp_path, capsys):
    out = tmp_path / "cli"
    assert dryrun.main(["--out", str(out), "--pairs", "1", "--blinded-pairs", "0", "--no-progress"]) == 0
    text = capsys.readouterr().out
    assert "greedy:" in text and "random:" in text and "check each with" in text
    assert dryrun.main(["--out", str(out), "--pairs", "1", "--blinded-pairs", "0", "--no-progress"]) == 2   # logs are there now
    assert "already holds logs" in capsys.readouterr().err
    src = next((out / "logs" / "scripted-greedy").glob("*-stakes.jsonl.gz"))
    assert dryrun.main(["--faulted-copy", str(src), str(tmp_path / "f")]) == 0
    assert (tmp_path / "f" / src.name).exists()
