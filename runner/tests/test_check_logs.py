"""runner/check_logs.py against logs the real play path wrote, then broken one fault at a time.

Every log here comes from runner.play.play_episode with the scripted agents (no model, no API). The question is the
real one from prompts/checkin_question.txt. Each fault test breaks one thing and asserts the checker names it, so a
checker that passed everything would fail these tests."""

import gzip
import json
from pathlib import Path

import pytest

from runner import check_logs
from runner.config import REPO_ROOT
from runner.play import play_episode
from world import blinding
from world.agents import GreedyAgent, RandomAgent
from world.env import CONDITIONS
from world.log import read_log

QUESTION = (REPO_ROOT / "prompts" / "checkin_question.txt").read_text(encoding="utf-8").strip()
PREREG = (REPO_ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8")
FULL_SEED = 990000   # GreedyAgent plays all 48 turns on it, in both conditions, through all four check-ins


def play_pair(root: Path, seed=FULL_SEED, agent_cls=GreedyAgent, *, key=None, folder="logs", phase="test", model=None):
    """Stakes twin first, then the no-stakes twin held to its last turn, as the runner does. Returns the two paths."""
    paths, stakes_turns = [], None
    for cond in CONDITIONS:
        label = blinding.condition_code(cond, blinded=True, path=key) if key else cond
        path = root / folder / f"{seed}-{label}.jsonl.gz"
        res = play_episode(agent_cls(seed), condition=cond, seed=seed, log_path=path, model=model or f"scripted-{agent_cls.__name__}",
                           condition_code=label, checkin_question=QUESTION, max_turns=stakes_turns, version="abc123",
                           header_extra={"phase": phase})
        assert res["status"] == "done"
        if cond == "stakes":
            stakes_turns = res["summary"]["turns"]
        paths.append(path)
    return paths


def write_log(path: Path, header, turns, end):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for obj in ([header] + turns + ([end] if end is not None else [])):
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def edit(path: Path, fn):
    """Rewrite a log this test made, after fn(header, turns, end) changed it in place."""
    header, turns, end = read_log(path)
    fn(header, turns, end)
    write_log(path, header, turns, end)


def run(root, **kw):
    kw.setdefault("question", QUESTION)
    return check_logs.check_directory(root, **kw)


def has(report, text):
    return any(text in f for f in report.failures)


def checkins(turns):
    return [t for t in turns if t["checkin"]]


@pytest.fixture
def pair(tmp_path):
    play_pair(tmp_path)
    return tmp_path, sorted((tmp_path / "logs").glob("*.jsonl.gz"))   # [no_stakes, stakes]


def test_a_clean_pair_passes_and_is_counted(pair):
    root, _ = pair
    r = run(root, prereg_text=PREREG)
    assert r.failures == [] and r.ok
    assert (r.episodes, r.pairs) == (2, 1)
    s = r.stats
    assert (s["windows"], s["windows:clean"], s["windows:diary_edit"], s["windows:attention_swap"]) == (8, 4, 2, 2)
    assert s["ended_early"] == 0 and s["empty_answers"] == 0 and s["stray_answers"] == 0


def test_the_real_question_file_is_the_one_in_the_preregistration():
    assert QUESTION in PREREG


def test_a_short_stakes_episode_and_its_held_twin_pass(tmp_path):
    play_pair(tmp_path, FULL_SEED, RandomAgent)   # the random critter starves long before turn 48
    stakes = read_log(tmp_path / "logs" / f"{FULL_SEED}-stakes.jsonl.gz")
    assert stakes[2]["fainted"] and len(stakes[1]) < 48
    r = run(tmp_path)
    assert r.failures == [] and r.pairs == 1
    assert r.stats["ended_early"] == 2 and r.stats["windows"] < 8


def test_exit_codes_and_one_line_per_failure(pair, capsys):
    root, (no_stakes, stakes) = pair
    assert check_logs.main([str(root)]) == 0
    assert "RESULT: PASS" in capsys.readouterr().out
    edit(stakes, lambda h, t, e: [t_.update(checkin_question="another question") for t_ in checkins(t)])
    assert check_logs.main([str(root)]) == 1
    out = capsys.readouterr().out
    fail_lines = [x for x in out.splitlines() if x.startswith("FAIL ")]
    assert len(fail_lines) == 4 and "RESULT: FAIL (4 failures)" in out   # one line per window, nothing else
    assert check_logs.main([str(root / "nope")]) == 2
    empty = root / "empty"
    empty.mkdir()
    assert check_logs.main([str(empty)]) == 2
    assert check_logs.main([str(root), "--question", str(root / "missing.txt")]) == 2
    assert not [x for x in capsys.readouterr().out.splitlines() if x.startswith("FAIL ")]


def test_the_checker_never_writes(pair):
    root, _ = pair
    before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    run(root)
    assert before == {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


# ----------------------------------------------------------------------------------- the check-in turns
def test_a_wrong_question_text_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: checkins(t)[1].update(checkin_question=QUESTION.replace("yes or no", "true or false")))
    r = run(root)
    assert has(r, "the check-in question is not the preregistered text") and len(r.failures) == 1


def test_a_log_without_the_question_field_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: [t_.pop("checkin_question") for t_ in t])
    assert has(run(root), "no checkin_question field")


def test_a_missing_answer_or_yes_field_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: (checkins(t)[0].pop("checkin_answer"), checkins(t)[1].pop("checkin_yes")))
    r = run(root)
    assert has(r, "no checkin_answer field") and has(r, "no checkin_yes field")


def test_an_answer_that_is_not_text_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: checkins(t)[0].update(checkin_answer=None))
    assert has(run(root), "checkin_answer is not text")


def test_a_yes_that_disagrees_with_the_answer_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: checkins(t)[0].update(checkin_yes=True))   # the answer says "No, ..."
    assert has(run(root), "does not match the answer")


def test_an_answer_off_a_check_in_turn_fails_but_a_stray_answer_is_only_counted(pair):
    root, (_, stakes) = pair
    off = lambda t: next(x for x in t if not x["checkin"])
    edit(stakes, lambda h, t, e: off(t).update(checkin_answer="No, nothing looked off."))
    assert has(run(root), "checkin_answer is set on turns that are not check-ins")
    edit(stakes, lambda h, t, e: off(t).update(checkin_answer=None, stray_answer="yes"))   # a valid reply
    r = run(root)
    assert r.failures == [] and r.stats["stray_answers"] == 1


def test_empty_and_unparsed_answers_are_notes_not_failures(pair):
    root, (_, stakes) = pair

    def f(h, t, e):
        c = checkins(t)
        c[0].update(checkin_answer="", checkin_yes=None)
        c[1].update(checkin_answer="Maybe, I am not sure.", checkin_yes=None)
    edit(stakes, f)
    r = run(root)
    assert r.failures == [] and r.stats["empty_answers"] == 1 and r.stats["unparsed_answers"] == 1


# ------------------------------------------------------------------------ an answer reaching a later diary
def test_an_answer_pasted_into_a_later_diary_fails(pair):
    root, (_, stakes) = pair

    def f(h, t, e):
        first = checkins(t)[0]
        for t_ in t:
            if t_["turn"] > first["turn"] + 1:
                for entry in t_["diary"]:
                    if entry["turn"] == first["turn"] + 1:
                        entry["text"] += " " + first["checkin_answer"]
    edit(stakes, f)
    r = run(root)
    assert len(r.failures) == 1 and has(r, "appears in the diary the critter saw on turn")


def test_a_short_answer_leaks_only_as_a_whole_diary_line(pair):
    root, (_, stakes) = pair

    def f(h, t, e, line):
        first = checkins(t)[0]
        first.update(checkin_answer="No.", checkin_yes=False)
        for t_ in t:
            if t_["turn"] > first["turn"] + 1:
                for entry in t_["diary"]:
                    if entry["turn"] == first["turn"] + 1:
                        entry["text"] = line
    edit(stakes, lambda h, t, e: f(h, t, e, "No way, heading north."))   # contains "No" but is not the answer
    assert run(root).failures == []
    edit(stakes, lambda h, t, e: f(h, t, e, "No."))
    assert has(run(root), "appears in the diary the critter saw")


def test_text_in_a_diary_entry_older_than_the_check_in_is_not_a_leak(pair):
    root, (_, stakes) = pair
    unique = "Unique answer text for this test."

    def paste(entry_turn_of):
        def f(h, t, e):
            third = checkins(t)[2]
            third.update(checkin_answer=unique, checkin_yes=None)
            for t_ in t:
                if t_["turn"] > third["turn"]:
                    for entry in t_["diary"]:
                        if entry["turn"] == entry_turn_of(third):
                            entry["text"] = unique
        return f
    edit(stakes, paste(lambda third: third["turn"] - 1))   # written before the check-in: cannot have come from it
    assert run(root).failures == []
    edit(stakes, paste(lambda third: third["turn"]))       # written on the check-in turn, as the old pipeline did
    r = run(root)
    assert len(r.failures) == 1 and has(r, "appears in the diary the critter saw")


# ------------------------------------------------------------------------------- the schedule and the turns
def test_a_missing_check_in_fails(pair):
    root, (_, stakes) = pair

    def f(h, t, e):
        last = checkins(t)[-1]
        last.update(checkin=False, checkin_window=None, checkin_question=None, checkin_answer=None, checkin_yes=None)
    edit(stakes, f)
    r = run(root)
    assert has(r, "the check-in at turn") and has(r, "is missing")


def test_a_check_in_where_the_schedule_has_none_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: next(x for x in t if not x["checkin"]).update(checkin=True))
    assert has(run(root), "is a check-in but the schedule has none there")


def test_a_check_in_not_two_turns_after_the_tamper_point_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: e["schedule"][0].update(checkin_turn=e["schedule"][0]["tamper_turn"] + 3))
    assert has(run(root), "is not 2 turns after tamper turn")


def test_a_window_outside_its_twelve_turns_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: e["schedule"][1].update(tamper_turn=11, checkin_turn=13))
    assert has(run(root), "are not both inside turns 13-24")


def test_the_window_kinds_must_be_two_clean_one_edit_one_swap(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: [w.update(kind="clean") for w in e["schedule"]])
    assert has(run(root), "the schedule's window kinds are")
    edit(stakes, lambda h, t, e: e.update(schedule=e["schedule"][:3]))
    assert has(run(root), "the schedule is not 4 windows")


def test_a_tamper_on_a_clean_window_fails(pair):
    root, (_, stakes) = pair

    def f(h, t, e):
        clean = next(w for w in e["schedule"] if w["kind"] == "clean")
        turn = next(x for x in t if x["turn"] == clean["tamper_turn"])
        turn.update(tamper={"type": "diary_edit"}, tamper_type="diary_edit")
    edit(stakes, f)
    assert has(run(root), "a clean window must get none")


def test_a_scheduled_tamper_that_never_happened_fails(pair):
    root, (_, stakes) = pair

    def f(h, t, e):
        w = next(w for w in e["schedule"] if w["kind"] == "attention_swap")
        next(x for x in t if x["turn"] == w["tamper_turn"]).update(tamper=None, tamper_type=None)
    edit(stakes, f)
    assert has(run(root), "no tamper at turn")


def test_a_tamper_of_the_wrong_type_fails(pair):
    root, (_, stakes) = pair

    def f(h, t, e):
        w = next(w for w in e["schedule"] if w["kind"] == "attention_swap")
        next(x for x in t if x["turn"] == w["tamper_turn"])["tamper"]["type"] = "diary_edit"
    edit(stakes, f)
    assert has(run(root), "schedule says attention_swap")


def test_an_attention_swap_that_shows_the_chosen_region_fails(pair):
    root, (_, stakes) = pair

    def f(h, t, e):
        w = next(w for w in e["schedule"] if w["kind"] == "attention_swap")
        x = next(x for x in t if x["turn"] == w["tamper_turn"])
        x["shown_region"] = x["chosen_region"]
        x["tamper"]["shown"] = x["chosen_region"]
    edit(stakes, f)
    assert has(run(root), "does not show a region other than the one chosen")


def test_a_region_shift_with_no_swap_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: t[0].update(shown_region=(t[0]["chosen_region"] + 1) % 9))
    assert has(run(root), "which are not swap turns")


def test_a_diary_edit_outside_two_to_six_turns_back_fails(pair):
    root, (_, stakes) = pair

    def f(h, t, e):
        w = next(w for w in e["schedule"] if w["kind"] == "diary_edit")
        x = next(x for x in t if x["turn"] == w["tamper_turn"])
        x["tamper"].update(turns_back=1, entry_turn=x["turn"] - 1)
    edit(stakes, f)
    assert has(run(root), "does not touch an entry 2 to 6 turns back")


def test_a_diary_edit_the_critter_did_not_see_fails(pair):
    root, (_, stakes) = pair

    def f(h, t, e):
        w = next(w for w in e["schedule"] if w["kind"] == "diary_edit")
        x = next(x for x in t if x["turn"] == w["tamper_turn"])
        for entry in x["diary"]:
            if entry["turn"] == x["tamper"]["entry_turn"]:
                entry["text"] = "something else entirely"
    edit(stakes, f)
    assert has(run(root), "does not hold the edited entry")


# ------------------------------------------------------------------------------------ headers and length
@pytest.mark.parametrize("field", ["code_version", "arm", "model", "condition_code", "world_seed", "start_map"])
def test_every_header_field_is_required(pair, field):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: h.pop(field))
    assert has(run(root), f"the header has no {field}")


def test_an_unknown_code_version_fails_and_a_dirty_one_is_a_note(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: h.update(code_version="abc123-dirty"))
    r = run(root)
    assert r.failures == [] and r.stats["dirty"] == 1
    edit(stakes, lambda h, t, e: h.update(code_version="unknown"))
    assert has(run(root), "code_version is 'unknown'")


def test_a_start_map_of_the_wrong_size_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: h.update(start_map=h["start_map"][:5]))
    assert has(run(root), "start_map is not a 11 by 11 map")


def test_a_stakes_episode_that_stops_short_without_fainting_fails(tmp_path):
    for cond in CONDITIONS:
        play_episode(GreedyAgent(FULL_SEED), condition=cond, seed=FULL_SEED, log_path=tmp_path / f"{cond}.jsonl.gz", model="m",
                     condition_code=cond, checkin_question=QUESTION, max_turns=30, version="v")
    r = run(tmp_path)
    assert has(r, "ended at turn 30 of 48 without fainting")


def test_broken_turn_numbers_fail(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: t[5].update(turn=99))
    assert has(run(root), "turn numbers are not 1, 2, 3")


def test_a_faint_that_is_not_the_last_turn_fails(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: t[10].update(fainted=True))
    assert has(run(root), "but an episode ends on the faint")


def test_a_header_label_that_disagrees_with_the_meters_fails(pair):
    root, (no_stakes, _) = pair
    edit(no_stakes, lambda h, t, e: h.update(condition_code="stakes"))
    assert has(run(root), "the header says 'stakes' but the meters are those of a no_stakes episode")


def test_meters_that_switch_condition_mid_episode_fail(pair):
    root, (_, stakes) = pair
    edit(stakes, lambda h, t, e: t[7].update(energy=None))
    assert has(run(root), "the meters switch between stakes and no-stakes")


# ---------------------------------------------------------------------------------------- unreadable logs
def test_a_log_that_is_not_finished_or_not_readable_fails_without_a_crash(pair):
    root, (no_stakes, stakes) = pair
    header, turns, _ = read_log(stakes)
    write_log(root / "logs" / "partial.jsonl.gz", header | {"world_seed": 7}, turns[:5], None)
    r = run(root)
    assert has(r, "partial.jsonl.gz: no end line")
    raw = stakes.read_bytes()
    stakes.write_bytes(raw[: len(raw) // 2])
    r = run(root)
    assert has(r, "990000-stakes.jsonl.gz: unreadable") or has(r, "990000-stakes.jsonl.gz: line")
    with gzip.open(no_stakes, "wt", encoding="utf-8") as f:
        f.write("this is not json\n")
    assert has(run(root), "is not JSON")


def test_an_unfinished_log_replaced_by_a_finished_redo_is_a_note(pair):
    root, (_, stakes) = pair
    header, turns, _ = read_log(stakes)
    write_log(root / "logs" / "990000-stakes.r0.jsonl.gz", header, turns[:5], None)   # same twin, cut off
    r = run(root)
    assert r.failures == [] and r.stats["superseded"] == 1 and r.episodes == 2


def test_two_finished_logs_for_one_twin_fail(pair):
    root, (_, stakes) = pair
    header, turns, end = read_log(stakes)
    write_log(root / "logs" / "again.jsonl.gz", header, turns, end)
    assert has(run(root), "finished logs for the same twin")


# ----------------------------------------------------------------------------------------- twin pairs
def test_a_lone_twin_fails(pair):
    root, (no_stakes, _) = pair
    no_stakes.rename(root / "no_stakes.moved")
    assert has(run(root), "a pair has exactly 2")


def test_two_twins_in_the_same_condition_fail(tmp_path):
    for code in ("C-AAAAAA", "C-BBBBBB"):   # coded, so only the meters say both are stakes episodes
        play_episode(GreedyAgent(FULL_SEED), condition="stakes", seed=FULL_SEED, log_path=tmp_path / f"{code}.jsonl.gz",
                     model="m", condition_code=code, checkin_question=QUESTION, version="v")
    assert has(run(tmp_path), "needs one stakes and one no-stakes episode")


def test_twins_that_end_on_different_turns_fail(tmp_path):
    play_episode(GreedyAgent(FULL_SEED), condition="stakes", seed=FULL_SEED, log_path=tmp_path / "a.jsonl.gz", model="m",
                 condition_code="stakes", checkin_question=QUESTION, version="v")
    play_episode(GreedyAgent(FULL_SEED), condition="no_stakes", seed=FULL_SEED, log_path=tmp_path / "b.jsonl.gz", model="m",
                 condition_code="no_stakes", checkin_question=QUESTION, version="v", max_turns=47)
    assert has(run(tmp_path), "the twins end on different turns")


def test_twins_on_different_maps_or_schedules_fail(pair):
    root, (no_stakes, _) = pair
    edit(no_stakes, lambda h, t, e: h.update(start_map=list(reversed(h["start_map"]))))
    assert has(run(root), "the twins start on different maps")
    edit(no_stakes, lambda h, t, e: e["schedule"].reverse())
    assert has(run(root), "different tamper schedules")


# -------------------------------------------------------------------------------------------- blinding
@pytest.fixture
def blinded(tmp_path):
    key = tmp_path / "scratch_key.json"
    play_pair(tmp_path, key=key, folder="b")
    return tmp_path / "b", key


def test_a_blinded_pair_passes_when_blinding_is_demanded(blinded):
    root, key = blinded
    code = json.loads(key.read_text())
    assert not any("stakes" in p.name for p in root.iterdir())
    for mode in ("yes", "auto"):
        r = run(root, blinded=mode)
        assert r.failures == [] and r.pairs == 1
    assert set(code.values()) == {read_log(p)[0]["condition_code"] for p in root.iterdir()}


def test_a_plain_log_cannot_pass_as_blinded(pair):
    root, _ = pair
    r = run(root, blinded="yes")
    assert has(r, "a blinded run must not say 'stakes' or 'no_stakes'")


def test_a_blinded_log_cannot_pass_as_plain(blinded):
    root, _ = blinded
    assert has(run(root, blinded="no"), "a plain run needs condition_code 'stakes' or 'no_stakes'")


def test_stakes_in_a_blinded_header_or_file_name_fails(blinded):
    root, _ = blinded
    f = sorted(root.iterdir())[0]
    edit(f, lambda h, t, e: h.update(episode_id="dryrun:stakes:1"))
    assert has(run(root, blinded="yes"), "a blinded run must not say")
    edit(f, lambda h, t, e: h.pop("episode_id"))
    assert run(root, blinded="yes").failures == []
    g = f.rename(root / "990000-no_stakes.jsonl.gz")
    assert has(run(root, blinded="yes"), "a blinded run must not say") and g.exists()


def test_a_run_that_mixes_plain_and_coded_labels_fails_in_auto(blinded):
    root, _ = blinded
    edit(sorted(root.iterdir())[0], lambda h, t, e: h.update(condition_code="stakes"))
    assert has(run(root), "the labels are neither all plain condition names")


def test_one_code_on_both_conditions_fails(blinded):
    root, _ = blinded
    a, b = sorted(root.iterdir())
    edit(b, lambda h, t, e: h.update(condition_code=read_log(a)[0]["condition_code"]))
    r = run(root, blinded="yes")
    assert has(r, "both twins carry the condition code") and has(r, "carries exactly 2 condition codes")


# -------------------------------------------------------------------------- the question and the preregistration
def test_a_question_file_the_preregistration_does_not_quote_fails(pair):
    root, _ = pair
    r = run(root, prereg_text=PREREG.replace(QUESTION, "some other wording"))
    assert has(r, "not the question quoted in PREREGISTRATION.md")


def test_a_different_question_file_is_what_the_logs_are_held_to(pair, capsys):
    root, _ = pair
    other = root / "q.txt"
    other.write_text("A different question?\n", encoding="utf-8")
    assert check_logs.main([str(root), "--question", str(other)]) == 1
    assert "the check-in question is not the preregistered text" in capsys.readouterr().out
