"""Job 011: per-variant tables from diag2_results.json (and probe_turn1.json if present). CPU only.

    python arm2/diag2_summary.py [--dir M:\\Projects\\Lobster-Lab\\runs\\arm2\\diag2]

Writes SUMMARY.md in that folder and prints it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_DIR = Path(r"M:\Projects\Lobster-Lab\runs\arm2\diag2")
MOVES = ("north", "south", "east", "west", "stay", "eat")


def pooled_moves(eps: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in eps:
        for k, v in m["moves"].items():
            out[k] = out.get(k, 0) + v
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def variant_row(variant: str, eps: list[dict]) -> dict:
    n = len(eps)
    turns = sum(m["turns"] for m in eps)
    faints = [m["faint_turn"] for m in eps if m["fainted"]]
    return {
        "variant": variant, "episodes": n, "window": eps[0]["diary_window"],
        "food_per_ep": sum(m["food_eaten"] for m in eps) / n,
        "food_each": [m["food_eaten"] for m in eps],
        "faints": f"{len(faints)}/{n}", "faint_turns": sorted(faints),
        "survive_past_30": sum((not m["fainted"]) or m["faint_turn"] > 30 for m in eps),
        "cells_mean": sum(m["distinct_cells"] for m in eps) / n,
        "moves": pooled_moves(eps),
        "F_shown": f"{sum(m['turns_F_in_shown_region'] for m in eps)}/{turns}",
        "on_food": sum(m["turns_standing_on_food"] for m in eps),
        "ate_on_food": sum(m["ate_when_on_food"] for m in eps),
        "eats_on_empty": sum(m["eats_on_empty_cells"] for m in eps),
        "valid_rate": sum(m["valid_first_try"] for m in eps) / turns,
        "invalid_turns": sum(m["invalid_turns"] for m in eps),
        "repeat_share": sum(m["diary_repeats"] for m in eps) / max(1, sum(m["diary_lines"] for m in eps)),
        "repeats": f"{sum(m['diary_repeats'] for m in eps)}/{sum(m['diary_lines'] for m in eps)}",
    }


def render(res: dict, probe: dict | None) -> str:
    eps = res["episodes"]
    variants = sorted({m["variant"] for m in eps})
    rows = [variant_row(v, [m for m in eps if m["variant"] == v]) for v in variants]
    L = ["# Job 011 per-variant numbers (dev seeds, stakes, 48-turn cap)", ""]
    L += ["| var | win | food/ep (each) | faints (turns) | alive past t30 | cells | F in shown | on food / ate | eats on empty | valid 1st try | repeated diary lines |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['variant']} | {r['window']} | {r['food_per_ep']:.2f} ({', '.join(map(str, r['food_each']))}) | {r['faints']} ({', '.join(map(str, r['faint_turns']))}) "
                 f"| {r['survive_past_30']}/{r['episodes']} | {r['cells_mean']:.1f} | {r['F_shown']} | {r['on_food']} / {r['ate_on_food']} | {r['eats_on_empty']} "
                 f"| {r['valid_rate']:.3f} ({r['invalid_turns']} invalid) | {r['repeats']} = {r['repeat_share']:.2f} |")
    L += ["", "Move counts, pooled over each variant's episodes:", ""]
    for r in rows:
        L.append(f"- {r['variant']}: {json.dumps(r['moves'])}")
    L += ["", "Per episode:", "", "| ep | turns | faint | food | cells | moves | F in shown | on food | ate | eats on empty | valid | repeats |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in eps:
        L.append(f"| {m['variant']}{m['seed']} | {m['turns']} | {m['faint_turn'] or '-'} | {m['food_eaten']} | {m['distinct_cells']} | {m['moves']} | "
                 f"{m['turns_F_in_shown_region']} | {m['turns_standing_on_food']} | {m['ate_when_on_food']} | {m['eats_on_empty_cells']} | "
                 f"{m['valid_first_try']} | {m['diary_repeats']}/{m['diary_lines']} |")
    if probe:
        L += ["", f"# Turn-1 probe (seeds {probe['seeds'][0]} to {probe['seeds'][-1]})", "",
              "Mean P of each move word at the move slot. 'argmax' = seeds where that word was the top move.", ""]
        for v, d in probe["variants"].items():
            for case, c in d["cases"].items():
                mean = c["mean_prob"]
                if not mean:
                    L.append(f"- {v} (window {d['diary_window']}) {case}: nothing scored")
                    continue
                L.append(f"- {v} (window {d['diary_window']}, {'move first' if d['move_first'] else 'diary first'}) {case}, n={c['n_scored']}: "
                         + ", ".join(f"{m} {mean[m]:.3f}" for m in MOVES) + f" | argmax {json.dumps({m: k for m, k in c['argmax_count'].items() if k})}"
                         + f" | mass on the six {c['mean_mass_on_the_six']:.3f}")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    args = ap.parse_args(argv)
    d = Path(args.dir)
    res = json.loads((d / "diag2_results.json").read_text(encoding="utf-8"))
    pp = d / "probe_turn1.json"
    text = render(res, json.loads(pp.read_text(encoding="utf-8")) if pp.exists() else None)
    (d / "SUMMARY.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
