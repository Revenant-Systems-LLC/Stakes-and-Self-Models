"""Check finished episode logs against the protocol in PREREGISTRATION.md.

    python -m runner.check_logs LOG_DIR [--blinded auto|yes|no]

LOG_DIR is searched for *.jsonl.gz, so it can be one phase's logs (runs/pilot/logs), one tier's, or a
dry-run folder. It reads the logs and nothing else: no config, no ledger, no manifest, no blinding key. It
never writes. One line is printed per failure, then a summary. Exit code 0 if nothing failed, 1 if anything
did, 2 if LOG_DIR has no logs to check or a text file it needs cannot be read.

What is checked.

Per episode
  * the header has the code version, arm, model, condition code, world seed and start map;
  * the log is finished (an end line with status "done") and has 48 turns, numbered 1 to N in order, unless
    the stakes critter fainted: then it ends on the faint, and its twin is held to that turn (per pair);
  * the end line's schedule is four windows of 12 turns, two clean, one diary edit and one attention swap
    (so exactly two tampered), and each check-in falls two turns after its tamper point (or the matching
    turn of a clean window) inside the same window;
  * the turns agree with the schedule: a check-in on every scheduled check-in turn the episode reached and
    nowhere else, a tamper on exactly the tampered windows' tamper turns it reached, of the scheduled type,
    and nothing on clean windows. An attention swap really shows another region than the one chosen, and
    only then. A diary edit touched an entry 2 to 6 turns back and the critter's diary shows the edited text;
  * every check-in turn carries the preregistered question text, word for word (checkin_question, the text
    the critter was sent), and has checkin_answer (text) and checkin_yes (as parse_yes_no reads it). Other
    turns have no question, no answer and no yes/no;
  * the answer text of a check-in appears in no later diary entry (one written on the check-in turn or after;
    an older entry cannot hold it). The observation's only free text is the diary
    (the rest is the map, the meters and the turn number), so the logged diary of every later turn is the
    later observation. An answer under 8 characters ("No.") counts only when a diary line is exactly that.

Per twin pair (same model and world seed)
  * exactly two finished logs, one stakes and one no-stakes, with different condition codes, the same
    start map and tamper schedule, and the same last turn.

Per run
  * Plain run: every header says "stakes" or "no_stakes", and the label agrees with the meters in the log.
  * Blinded run (--blinded yes): every header carries a code and nothing in a header or file name says
    "stakes" or "no_stakes"; exactly two codes appear; each code is always the same condition.
  * --blinded auto (the default) takes a run with only plain names as plain and one with none as blinded,
    and fails a run that mixes the two. Pass --blinded yes for a confirmatory run so a plain-labelled log
    cannot pass as plain.
  * The question the logs are held to is prompts/checkin_question.txt, and it is the question quoted in
    PREREGISTRATION.md.

Not failures, counted in the summary: a check-in the critter left empty (checkin_answer ""), an answer that
does not start with yes or no, an answer given off a check-in turn (stray_answer), a log written from a work
tree with uncommitted changes (code version ends in "-dirty"), and an unfinished log that a finished log of
the same episode replaced (a resumed run).

The protocol numbers below come from PREREGISTRATION.md and are written out here on purpose, not imported
from world/, so a drift in the world shows up as a failure here.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from runner.config import REPO_ROOT
from runner.play import parse_yes_no

EPISODE_TURNS = 48
WINDOW_LEN = 12
N_WINDOWS = 4
CHECKIN_GAP = 2
KIND_COUNTS = {"clean": 2, "diary_edit": 1, "attention_swap": 1}
CONDITION_NAMES = ("stakes", "no_stakes")
HEADER_FIELDS = ("code_version", "arm", "model", "condition_code", "world_seed", "start_map")
MAP_SIZE = 11
SHORT_ANSWER = 8   # answers shorter than this only count as a leak when a diary line is exactly the answer
DEFAULT_QUESTION = REPO_ROOT / "prompts" / "checkin_question.txt"
DEFAULT_PREREG = REPO_ROOT / "PREREGISTRATION.md"


@dataclass
class Episode:
    path: Path
    name: str                                   # path relative to the log directory
    header: dict | None = None
    turns: list = field(default_factory=list)
    end: dict | None = None
    fails: list = field(default_factory=list)
    stats: Counter = field(default_factory=Counter)
    condition: str | None = None                # "stakes" or "no_stakes", read from the meters in the log

    @property
    def finished(self) -> bool:
        return self.header is not None and self.end is not None and self.end.get("status") == "done"

    @property
    def code(self):
        return (self.header or {}).get("condition_code")


@dataclass
class Report:
    failures: list
    stats: Counter
    episodes: int = 0
    pairs: int = 0

    @property
    def ok(self) -> bool:
        return not self.failures


def load_episode(path: Path, root: Path) -> Episode:
    ep = Episode(path, path.relative_to(root).as_posix())
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                try:
                    obj = json.loads(line)
                except ValueError as e:
                    ep.fails.append(f"line {n} is not JSON ({e})")
                    return ep
                kind = obj.get("type") if isinstance(obj, dict) else None
                if n == 1 and kind != "header":
                    ep.fails.append("the first line is not a header")
                    return ep
                if kind == "header" and n == 1:
                    ep.header = obj
                elif kind == "turn" and ep.header is not None and ep.end is None:
                    ep.turns.append(obj)
                elif kind == "end" and ep.end is None:
                    ep.end = obj
                else:
                    ep.fails.append(f"line {n}: unexpected {kind!r} line")
                    return ep
    except (OSError, EOFError, ValueError) as e:   # includes a gzip cut off mid-write
        ep.fails.append(f"unreadable: {type(e).__name__}: {e}")
    return ep


def _leaks(answer: str, line: str) -> bool:
    return answer in line if len(answer) >= SHORT_ANSWER else answer == line.strip()


def _turns_text(nums) -> str:
    nums = list(nums)
    return ", ".join(map(str, nums[:6])) + (f" and {len(nums) - 6} more" if len(nums) > 6 else "")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _schedule(sched, fail):
    """The end line's schedule if it is four sound windows, else None (with the reasons failed)."""
    if not isinstance(sched, list) or len(sched) != N_WINDOWS or not all(isinstance(w, dict) for w in sched):
        fail(f"the schedule is not {N_WINDOWS} windows")
        return None
    ok = True
    for i, w in enumerate(sched):
        lo, hi = WINDOW_LEN * i + 1, WINDOW_LEN * (i + 1)
        t, c = w.get("tamper_turn"), w.get("checkin_turn")
        if w.get("window") != i or not _int(t) or not _int(c):
            fail(f"schedule window {i}: bad window index or turns ({w})")
            ok = False
        elif not (lo <= t and c <= hi):
            fail(f"schedule window {i}: tamper turn {t} and check-in turn {c} are not both inside turns {lo}-{hi}")
            ok = False
        elif c != t + CHECKIN_GAP:
            fail(f"schedule window {i}: check-in turn {c} is not {CHECKIN_GAP} turns after tamper turn {t}")
            ok = False
    kinds = Counter(w.get("kind") for w in sched)
    if kinds != Counter(KIND_COUNTS):
        fail(f"the schedule's window kinds are {dict(kinds)}, need {KIND_COUNTS} (two clean, one diary edit, one attention swap)")
        ok = False
    return sched if ok else None


def check_episode(ep: Episode, question: str) -> None:
    """Fill ep.fails, ep.stats and ep.condition."""
    fail = ep.fails.append
    h, turns, end = ep.header, ep.turns, ep.end
    if h is None:
        return
    for k in HEADER_FIELDS:
        if k not in h or h[k] is None or h[k] == "" or h[k] == []:
            fail(f"the header has no {k}")
    if h.get("code_version") == "unknown":
        fail("the header's code_version is 'unknown' (git could not be read)")
    if isinstance(h.get("code_version"), str) and h["code_version"].endswith("-dirty"):
        ep.stats["dirty"] += 1
    if "world_seed" in h and not _int(h["world_seed"]):
        fail(f"the header's world_seed is not an integer ({h['world_seed']!r})")
    sm = h.get("start_map")
    if sm and not (isinstance(sm, list) and len(sm) == MAP_SIZE and all(isinstance(r, str) and len(r) == MAP_SIZE for r in sm)):
        fail(f"the header's start_map is not a {MAP_SIZE} by {MAP_SIZE} map")
    if end is None:
        fail("no end line: the episode crashed or is still running")
        return
    if end.get("status") != "done":
        fail(f"the episode did not finish (status {end.get('status')!r})")
        return
    if not turns:
        fail("no turns")
        return

    n = len(turns)
    if [t.get("turn") for t in turns] != list(range(1, n + 1)):
        fail("turn numbers are not 1, 2, 3 ... in order")
        return
    if end.get("turns") != n:
        fail(f"the end line says {end.get('turns')} turns but the log has {n}")
    if n > EPISODE_TURNS:
        fail(f"{n} turns, more than the {EPISODE_TURNS} of an episode")

    # the condition, from the meters, and the header's label if it is a plain one
    stakes_like = turns[0].get("energy") is not None
    ep.condition = "stakes" if stakes_like else "no_stakes"
    bad = [t["turn"] for t in turns
           if (t.get("energy") is None) == stakes_like or (t.get("health") is None) == stakes_like
           or (t.get("points") is None) != stakes_like]
    if bad:
        fail(f"the meters switch between stakes and no-stakes on turns {_turns_text(bad)}")
    if h.get("condition_code") in CONDITION_NAMES and h["condition_code"] != ep.condition:
        fail(f"the header says {h['condition_code']!r} but the meters are those of a {ep.condition} episode")

    # length and faint
    fainted = [t["turn"] for t in turns if t.get("fainted")]
    if ep.condition == "stakes":
        if fainted not in ([], [n]):
            fail(f"fainted on turn {_turns_text(fainted)}, but an episode ends on the faint (last turn {n})")
        if n < EPISODE_TURNS and fainted != [n]:
            fail(f"ended at turn {n} of {EPISODE_TURNS} without fainting")
        if bool(end.get("fainted")) != (fainted == [n]):
            fail("the end line's fainted disagrees with the turns")
    else:
        if fainted or end.get("fainted"):
            fail("a no-stakes episode fainted")
    if n < EPISODE_TURNS:
        ep.stats["ended_early"] += 1

    sched = _schedule(end.get("schedule"), fail)
    if sched is None:
        return
    by_turn = {t["turn"]: t for t in turns}

    # check-in turns against the schedule
    expected = {w["checkin_turn"]: w for w in sched if w["checkin_turn"] <= n}
    observed = sorted(t["turn"] for t in turns if t.get("checkin"))
    for tt in sorted(set(expected) - set(observed)):
        w = expected[tt]
        fail(f"window {w['window']} ({w['kind']}): the check-in at turn {tt} is missing")
    for tt in sorted(set(observed) - set(expected)):
        fail(f"turn {tt} is a check-in but the schedule has none there")
    for tt in sorted(set(observed) & set(expected)):
        w = expected[tt]
        if by_turn[tt].get("checkin_window") != w["window"]:
            fail(f"turn {tt}: checkin_window is {by_turn[tt].get('checkin_window')!r}, the schedule says {w['window']}")
        ep.stats["windows"] += 1
        ep.stats[f"windows:{w['kind']}"] += 1

    # tamper turns against the schedule
    exp_tamper = {w["tamper_turn"]: w for w in sched if w["kind"] != "clean" and w["tamper_turn"] <= n}
    obs_tamper = {t["turn"]: t for t in turns if t.get("tamper")}
    for tt in sorted(set(exp_tamper) - set(obs_tamper)):
        fail(f"window {exp_tamper[tt]['window']} ({exp_tamper[tt]['kind']}): no tamper at turn {tt}")
    for tt in sorted(set(obs_tamper) - set(exp_tamper)):
        fail(f"turn {tt}: a tamper ({obs_tamper[tt]['tamper'].get('type')}) the schedule does not have there "
             f"(a clean window must get none)")
    for tt in sorted(set(obs_tamper) & set(exp_tamper)):
        w, t = exp_tamper[tt], obs_tamper[tt]
        tam = t["tamper"]
        if tam.get("type") != w["kind"] or t.get("tamper_type") != w["kind"]:
            fail(f"turn {tt}: tamper is {tam.get('type')!r} (tamper_type {t.get('tamper_type')!r}), schedule says {w['kind']}")
            continue
        if w["kind"] == "attention_swap":
            if not (tam.get("chosen") == t.get("chosen_region") and tam.get("shown") == t.get("shown_region")
                    and t.get("shown_region") != t.get("chosen_region")):
                fail(f"turn {tt}: the attention swap does not show a region other than the one chosen")
        else:
            back, entry = tam.get("turns_back"), tam.get("entry_turn")
            if not (_int(back) and 2 <= back <= 6 and entry == tt - back):
                fail(f"turn {tt}: the diary edit does not touch an entry 2 to 6 turns back (turns_back {back!r}, entry_turn {entry!r})")
            elif tam.get("before") == tam.get("after"):
                fail(f"turn {tt}: the diary edit changed nothing")
            elif not any(e.get("turn") == entry and e.get("text") == tam.get("after") for e in t.get("diary", [])):
                fail(f"turn {tt}: the diary the critter saw does not hold the edited entry from turn {entry}")
    stray_shift = [t["turn"] for t in turns
                   if t["turn"] not in {tt for tt, w in exp_tamper.items() if w["kind"] == "attention_swap"}
                   and t.get("shown_region") != t.get("chosen_region")]
    if stray_shift:
        fail(f"the region shown differs from the region chosen on turns {_turns_text(stray_shift)}, which are not swap turns")

    # the check-in turns' fields, and what the other turns must not have
    for tt in observed:
        t = by_turn[tt]
        if "checkin_question" not in t:
            fail(f"turn {tt}: no checkin_question field (a log from before the question was logged?)")
        elif t["checkin_question"] != question:
            fail(f"turn {tt}: the check-in question is not the preregistered text: {str(t['checkin_question'])[:80]!r}")
        for key in ("checkin_answer", "checkin_yes"):
            if key not in t:
                fail(f"turn {tt}: no {key} field")
        ans = t.get("checkin_answer")
        if "checkin_answer" in t and not isinstance(ans, str):
            fail(f"turn {tt}: checkin_answer is not text ({ans!r})")
        elif isinstance(ans, str) and "checkin_yes" in t:
            if t["checkin_yes"] != parse_yes_no(ans):
                fail(f"turn {tt}: checkin_yes {t['checkin_yes']!r} does not match the answer {ans[:40]!r}")
            if not ans.strip():
                ep.stats["empty_answers"] += 1
            elif t["checkin_yes"] is None:
                ep.stats["unparsed_answers"] += 1
        if t.get("stray_answer"):
            fail(f"turn {tt}: stray_answer is set on a check-in turn")
    for key in ("checkin_question", "checkin_answer", "checkin_yes"):
        off = [t["turn"] for t in turns if not t.get("checkin") and t.get(key) is not None]
        if off:
            fail(f"{key} is set on turns that are not check-ins: {_turns_text(off)}")
    ep.stats["stray_answers"] += sum(1 for t in turns if t.get("stray_answer"))

    # no answer text in any later diary
    for tt in observed:
        ans = by_turn[tt].get("checkin_answer")
        ans = ans.strip() if isinstance(ans, str) else ""
        if not ans:
            continue
        hits = []   # (turn the critter saw it on, turn of the diary entry that holds it)
        for t in turns:
            if t["turn"] > tt:
                # only entries written on the check-in turn or after it can hold this answer
                e = next((e for e in t.get("diary", [])
                          if _int(e.get("turn")) and e["turn"] >= tt and _leaks(ans, str(e.get("text", "")))), None)
                if e is not None:
                    hits.append((t["turn"], e.get("turn")))
        if hits:
            fail(f"the check-in answer of turn {tt} ({ans[:40]!r}) appears in the diary the critter saw on turn "
                 f"{hits[0][0]} (entry from turn {hits[0][1]}) and on {len(hits) - 1} later turns")


def check_pairs(episodes: list[Episode]) -> tuple[list[str], int]:
    """Failures for twin pairs, and the number of sound pairs. Only finished episodes are paired."""
    groups = defaultdict(list)
    for ep in episodes:
        if ep.finished:
            h = ep.header
            groups[(h.get("phase"), h.get("model"), h.get("world_seed"))].append(ep)
    fails, pairs = [], 0
    for (phase, model, seed), g in sorted(groups.items(), key=lambda kv: str(kv[0])):
        where = f"pair {model} seed {seed}" + (f" ({phase})" if phase else "")
        if len(g) != 2:
            fails.append(f"{where}: {len(g)} finished logs ({', '.join(e.name for e in g)}); a pair has exactly 2")
            continue
        a, b = g
        if sorted(str(e.condition) for e in g) != ["no_stakes", "stakes"]:
            fails.append(f"{where}: needs one stakes and one no-stakes episode, found {[e.condition for e in g]}")
            continue
        pairs += 1
        if a.code == b.code:
            fails.append(f"{where}: both twins carry the condition code {a.code!r}")
        if a.header.get("start_map") != b.header.get("start_map"):
            fails.append(f"{where}: the twins start on different maps")
        if a.end.get("schedule") != b.end.get("schedule"):
            fails.append(f"{where}: the twins have different tamper schedules")
        if len(a.turns) != len(b.turns):
            fails.append(f"{where}: the twins end on different turns ({a.name}: {len(a.turns)}, {b.name}: {len(b.turns)})")
    return fails, pairs


def check_run(episodes: list[Episode], mode: str) -> list[str]:
    """Run-level failures: how the condition is labelled. mode is "auto", "yes" (blinded) or "no" (plain)."""
    eps = [e for e in episodes if e.header is not None]
    codes = [str(e.code) for e in eps]
    fails = []
    plain = [c in CONDITION_NAMES for c in codes]
    if mode == "auto":
        if all(plain):
            mode = "no"
        elif not any(plain) and not any("stakes" in c.lower() for c in codes):
            mode = "yes"
        else:
            n_plain = sum(plain)
            fails.append(f"run: the labels are neither all plain condition names ({n_plain} logs are) nor all codes; "
                         f"{len(codes) - n_plain} logs carry something else")
            return fails
    if mode == "no":
        for e, c in zip(eps, codes):
            if c not in CONDITION_NAMES:
                fails.append(f"{e.name}: a plain run needs condition_code 'stakes' or 'no_stakes', found {c!r}")
        return fails
    for e, c in zip(eps, codes):
        if "stakes" in json.dumps(e.header, ensure_ascii=False).lower() or "stakes" in e.name.lower():
            fails.append(f"{e.name}: a blinded run must not say 'stakes' or 'no_stakes' in a header or file name "
                         f"(condition_code {c!r})")
    distinct = sorted(set(codes))
    if len(distinct) != 2:
        fails.append(f"run: a blinded run carries exactly 2 condition codes, found {len(distinct)}: {distinct[:6]}")
    meaning = defaultdict(set)
    for e, c in zip(eps, codes):
        if e.condition:
            meaning[c].add(e.condition)
    for c, conds in sorted(meaning.items()):
        if len(conds) > 1:
            fails.append(f"run: the code {c!r} is on both stakes and no-stakes episodes")
    return fails


def find_logs(root: Path) -> list[Path]:
    return sorted(root.rglob("*.jsonl.gz"))


def check_directory(root: str | Path, *, question: str, blinded: str = "auto", prereg_text: str | None = None) -> Report:
    """Check every log under root. question is the exact text the logs must carry (already stripped)."""
    root = Path(root)
    loaded = [load_episode(p, root) for p in find_logs(root)]
    # a resumed run leaves an unfinished log beside the finished redo of the same twin: that is not a failure
    by_twin = defaultdict(list)
    for ep in loaded:
        if ep.header is not None:
            h = ep.header
            by_twin[(h.get("phase"), h.get("model"), h.get("world_seed"), h.get("condition_code"))].append(ep)
    superseded, failures = [], []
    for g in by_twin.values():
        done = [e for e in g if e.finished]
        if done:
            superseded += [e for e in g if not e.finished]
            if len(done) > 1:
                failures.append(f"{done[0].name}: {len(done)} finished logs for the same twin ({', '.join(e.name for e in done)})")
    drop = {id(e) for e in superseded}
    episodes = [e for e in loaded if id(e) not in drop]

    for ep in episodes:
        try:
            check_episode(ep, question)
        except Exception as e:   # a log so malformed the checks cannot read it is a failure, not a crash
            ep.fails.append(f"could not be checked: {type(e).__name__}: {e}")
    pair_fails, pairs = check_pairs(episodes)
    failures += pair_fails + check_run(episodes, blinded)
    if prereg_text is not None and question not in prereg_text:
        failures.append("run: the check-in question file is not the question quoted in PREREGISTRATION.md")
    for ep in episodes:
        failures += [f"{ep.name}: {m}" for m in ep.fails]

    stats = Counter()
    for ep in episodes:
        stats.update(ep.stats)
    stats["superseded"] = len(superseded)
    return Report(failures, stats, episodes=len(episodes), pairs=pairs)


def summary_lines(report: Report, root: Path) -> list[str]:
    s = report.stats
    tampered = s["windows:diary_edit"] + s["windows:attention_swap"]
    lines = [
        f"checked {report.episodes} episodes ({report.pairs} twin pairs) in {root}",
        f"check-in windows: {s['windows']} ({tampered} tampered: {s['windows:diary_edit']} diary edit, "
        f"{s['windows:attention_swap']} attention swap; {s['windows:clean']} clean)",
        f"episodes ended early: {s['ended_early']}",
        f"notes (not failures): empty check-in answers {s['empty_answers']}, answers that are not yes or no "
        f"{s['unparsed_answers']}, stray answers {s['stray_answers']}, logs from a dirty work tree {s['dirty']}, "
        f"unfinished logs replaced by a finished redo {s['superseded']}",
        f"failures: {len(report.failures)}",
        "RESULT: PASS" if report.ok else f"RESULT: FAIL ({len(report.failures)} failures)",
    ]
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="runner.check_logs", description=__doc__.split("\n\n")[0], allow_abbrev=False)
    ap.add_argument("log_dir", help="a folder holding episode logs (*.jsonl.gz, searched recursively)")
    ap.add_argument("--blinded", choices=("auto", "yes", "no"), default="auto",
                    help="yes: the run must be blinded (codes only); no: plain names; auto: whichever the logs are, but not mixed")
    ap.add_argument("--question", default=str(DEFAULT_QUESTION), help="the check-in question file (default prompts/checkin_question.txt)")
    ap.add_argument("--prereg", default=str(DEFAULT_PREREG), help="PREREGISTRATION.md, which must quote the question")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    root = Path(args.log_dir)
    if not root.is_dir():
        print(f"error: {root} is not a folder", file=sys.stderr, flush=True)
        return 2
    if not find_logs(root):
        print(f"error: no *.jsonl.gz logs under {root}", file=sys.stderr, flush=True)
        return 2
    try:
        question = Path(args.question).read_text(encoding="utf-8").strip()
        prereg_text = Path(args.prereg).read_text(encoding="utf-8")
    except OSError as e:
        print(f"error: cannot read {e.filename}: {e.strerror}", file=sys.stderr, flush=True)
        return 2
    if not question:
        print(f"error: {args.question} is empty", file=sys.stderr, flush=True)
        return 2
    report = check_directory(root, question=question, blinded=args.blinded, prereg_text=prereg_text)
    for line in report.failures:
        print(f"FAIL {line}", flush=True)
    for line in summary_lines(report, root):
        print(line, flush=True)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
