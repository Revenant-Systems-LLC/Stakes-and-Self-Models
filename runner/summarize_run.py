"""Validity and cost summary of one phase's run folder, by tier and condition.

    python -m runner.summarize_run RUN_DIR

RUN_DIR is one phase folder, such as M:/Projects/Lobster-Lab/runs/pilot-attempt2. It reads
RUN_DIR/manifest.jsonl and every RUN_DIR/logs/*/*.jsonl.gz and never writes.

It reports what decides whether a run is usable and what the next phase costs: episodes and their status,
turns, faints, cost per episode, invalid turns, lenient replies, retries, refusals, empty check-in answers,
answers that don't start with yes or no, stray answers and blank diary lines. It does not count yes answers,
hits or false alarms, so reading it tells nothing about the hypotheses.

A blank diary line is a turn whose diary entry, as the critter sees it on the next turn, is empty. The last
turn's entry is never shown, so it is not counted.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from world.log import read_log


def blank_diary_lines(turns: list[dict]) -> tuple[int, int]:
    """(blank, counted): turn t's own entry as shown on turn t+1."""
    blank = counted = 0
    for prev, nxt in zip(turns, turns[1:]):
        t = prev.get("turn")
        for e in nxt.get("diary") or []:
            if e.get("turn") == t:
                counted += 1
                blank += not (e.get("text") or "").strip()
                break
    return blank, counted


def condition_of(header: dict, path: Path) -> str:
    code = header.get("condition_code") or path.name.split("-", 1)[-1].split(".", 1)[0]
    return str(code)


def summarize(run_dir: Path) -> dict:
    groups: dict[tuple[str, str], dict] = defaultdict(lambda: defaultdict(float))
    for path in sorted(run_dir.glob("logs/*/*.jsonl.gz")):
        tier = path.parent.name
        header, turns, end = read_log(path)
        header = header or {}
        g = groups[(tier, condition_of(header, path))]
        g["logs"] += 1
        if end is None:
            g["unfinished"] += 1
            continue
        g[f"status_{end.get('status')}"] += 1
        if end.get("status") != "done":
            continue
        g["episodes"] += 1
        g["turns"] += end.get("turns", 0)
        g["fainted"] += bool(end.get("fainted"))
        g["cost_usd"] += end.get("cost_usd", 0.0)
        g["invalid_turns"] += end.get("invalid_turns", 0)
        g["lenient_replies"] += end.get("lenient_replies", 0)
        g["refusals"] += end.get("refusals", 0)
        g["stray_answers"] += end.get("stray_answers", 0)
        g["empty_checkin_answers"] += end.get("empty_checkin_answers", 0)
        g["api_calls"] += end.get("api_calls", 0)
        g["tokens_in"] += end.get("tokens_in", 0)
        g["tokens_out"] += end.get("tokens_out", 0)
        checkins = [t for t in turns if t.get("checkin")]
        g["checkins"] += len(checkins)
        g["checkin_not_yes_no"] += sum(1 for t in checkins
                                       if (t.get("checkin_answer") or "").strip() and t.get("checkin_yes") is None)
        b, c = blank_diary_lines(turns)
        g["blank_diary"] += b
        g["diary_counted"] += c
        g["food_eaten"] += end.get("food_eaten", 0)
        g["max_episode_cost"] = max(g["max_episode_cost"], end.get("cost_usd", 0.0))
    manifest = run_dir / "manifest.jsonl"
    halts, excluded = [], 0
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("type") == "halt":
                halts.append(f"{r.get('reason')}: {r.get('detail')}")
            elif r.get("type") == "pair_excluded" and not str(r.get("reason", "")).startswith(("voided", "earlier attempt")):
                excluded += 1
    return {"groups": {k: dict(v) for k, v in groups.items()}, "halts": halts, "exclusions": excluded}


def _rate(n: float, d: float) -> str:
    return f"{n:.0f}/{d:.0f} ({100 * n / d:.1f}%)" if d else f"{n:.0f}/0"


def report(s: dict) -> list[str]:
    out = []
    tiers = sorted({t for t, _ in s["groups"]})
    for tier in tiers:
        for (t, cond), g in sorted(s["groups"].items()):
            if t != tier:
                continue
            n = g.get("episodes", 0)
            turns = g.get("turns", 0)
            out.append(f"{tier} {cond}: {n:.0f} done of {g.get('logs', 0):.0f} logs"
                       + (f", {g.get('unfinished', 0):.0f} unfinished" if g.get("unfinished") else ""))
            if not n:
                continue
            out.append(f"  turns mean {turns / n:.1f}, fainted {g.get('fainted', 0):.0f}, food eaten mean {g.get('food_eaten', 0) / n:.1f}")
            out.append(f"  cost mean ${g.get('cost_usd', 0) / n:.4f}, max ${g.get('max_episode_cost', 0):.4f}, "
                       f"total ${g.get('cost_usd', 0):.4f}, calls per turn {g.get('api_calls', 0) / turns:.2f}")
            out.append(f"  invalid turns {_rate(g.get('invalid_turns', 0), turns)}, lenient replies "
                       f"{_rate(g.get('lenient_replies', 0), turns)}, refusals {g.get('refusals', 0):.0f}")
            out.append(f"  blank diary lines {_rate(g.get('blank_diary', 0), g.get('diary_counted', 0))}")
            out.append(f"  check-ins {g.get('checkins', 0):.0f}, empty {g.get('empty_checkin_answers', 0):.0f}, "
                       f"not yes/no {g.get('checkin_not_yes_no', 0):.0f}, stray answers {g.get('stray_answers', 0):.0f}")
    out.append(f"exclusions (not counting seeds of earlier attempts): {s['exclusions']}")
    out.append("halts: " + ("; ".join(s["halts"]) if s["halts"] else "none"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="runner.summarize_run", description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir")
    args = ap.parse_args(argv)
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"error: {run_dir} is not a folder", file=sys.stderr)
        return 2
    for line in report(summarize(run_dir)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
