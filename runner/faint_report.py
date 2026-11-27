"""Why stakes critters fainted: one line per stakes episode in a phase folder.

    python -m runner.faint_report RUN_DIR

For each finished stakes episode (condition code "stakes"; a blinded run's codes are skipped) it prints the tier, seed, turns played, whether it fainted, energy and
health on its last turn, food eaten and thorns hit, and the cause: energy (energy reached 0), health
(health reached 0), or "-" for an episode that did not faint. A turn line shows the meters before that turn's
move, so the last line of a starved critter shows energy 1. Then a count of faints by cause per tier.
It reads RUN_DIR/logs/*/*-stakes*.jsonl.gz and never writes. It reads no check-in answer, so it says
nothing about the hypotheses.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

from world.log import read_log


def cause(end: dict, last: dict | None) -> str:
    """The end line's final meters decide it when they are there. Otherwise: a turn line holds the meters as the critter saw them before its move, and every move costs 1 energy. So a
    faint whose last line shows energy 1 or less was starvation, whatever happened to health. Otherwise it was
    health (a thorn on the last move)."""
    if not end.get("fainted"):
        return "-"
    fe, fh = end.get("final_energy"), end.get("final_health")
    if fe is not None and fh is not None:   # the end line's meters are after the last move
        return "both" if fe <= 0 and fh <= 0 else "energy" if fe <= 0 else "health" if fh <= 0 else "unknown"
    if last is None or last.get("energy") is None:
        return "unknown"
    return "energy" if last["energy"] <= 1 else "health"


def rows(run_dir: Path) -> list[dict]:
    out = []
    for path in sorted(run_dir.glob("logs/*/*.jsonl.gz")):
        header, turns, end = read_log(path)
        code = str((header or {}).get("condition_code") or "")
        if code != "stakes":
            continue
        if end is None or end.get("status") != "done":
            continue
        last = turns[-1] if turns else None
        out.append({
            "tier": path.parent.name, "seed": (header or {}).get("world_seed"), "file": path.name,
            "turns": end.get("turns"), "fainted": bool(end.get("fainted")),
            "energy": None if last is None else last.get("energy"),
            "health": None if last is None else last.get("health"),
            "food": end.get("food_eaten"), "thorns": end.get("thorns_hit"), "cause": cause(end, last),
        })
    return out


def report(rs: list[dict]) -> list[str]:
    lines = ["tier seed turns fainted energy health food thorns cause"]
    for r in rs:
        lines.append(f"{r['tier']} {r['seed']} {r['turns']} {'yes' if r['fainted'] else 'no'} {r['energy']} "
                     f"{r['health']} {r['food']} {r['thorns']} {r['cause']}")
    by = defaultdict(Counter)
    for r in rs:
        by[r["tier"]]["episodes"] += 1
        if r["fainted"]:
            by[r["tier"]][r["cause"]] += 1
    lines.append("faints by cause:")
    for tier in sorted(by):
        c = by[tier]
        lines.append(f"  {tier}: {c['episodes']} stakes episodes, energy {c['energy']}, health {c['health']}, "
                     f"both {c['both']}, unknown {c['unknown']}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="runner.faint_report", description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir")
    run_dir = Path(ap.parse_args(argv).run_dir)
    if not run_dir.is_dir():
        print(f"error: {run_dir} is not a folder", file=sys.stderr)
        return 2
    for line in report(rows(run_dir)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
