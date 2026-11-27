"""Job 011 turn-1 probe: how much probability does Qwen put on each move word when it picks its move?

    python arm2/diag2_probe.py [--seeds 990030-990049] [--variants R1,R2,R0,R4] [--out <dir>]

Same idea as job 009's diag_probe.py, but the reason-first variants write the diary and look before the move, so the
move slot is reached by sampling the reply (same sampling and per-turn seed as the episodes) up to the point where
it has written  "move": "  and then reading the next-token distribution there. For a move-first variant (R4) the
reply is forced to begin  {"move": "  as in 009. The six move words are compared on their first token.

Two cases per dev seed, turn 1, stakes, empty diary, region 4 shown:
  as dealt   the real turn-1 view
  food north the same view with an F put directly north of the critter (window row 3, column 4), which is in the
             region shown in detail; seeds where that cell is a wall are skipped

Dev seeds only, and none that job 009 used. No episode is played.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch
from tqdm import tqdm

from arm2.diag2 import (DEV_SEEDS, OUT_DEFAULT, SEEDS_009_USED, VARIANTS, Diag2Critter, status, variant_system, window_shown)
from arm2.qwen_critter import MODEL_ID, load_model, read_system_prompt, turn_seed
from world import observe
from world.env import MOVES, CritterWorld

MOVE_KEY = re.compile(r'"move"\s*:\s*"')
FORCED_PREFIX = '{"move": "'
CASES = ("as dealt", "food north")


def turn1_text(seed: int, window: int, case: str) -> str | None:
    """The turn-1 text the critter would see, or None if the case can't be built on this seed."""
    env = CritterWorld("stakes")
    env.reset(seed=seed)
    with window_shown(window):
        obs, _ = env.critter_view()
        assert env.shown_region == 4, f"seed {seed}: turn 1 shows region {env.shown_region}, expected 4"
        if case == "food north":
            row = obs["window"][3]
            if row[4] == "#":
                return None
            obs["window"][3] = row[:4] + "F" + row[5:]
        return observe.render_text(obs)


def move_distribution(model, tok, prompt_ids: list[int], prefix_text: str, first: dict[str, int]) -> dict[str, float]:
    ids = prompt_ids + tok(prefix_text, add_special_tokens=False)["input_ids"]
    with torch.no_grad():
        logits = model(input_ids=torch.tensor([ids], device=model.device)).logits[0, -1].float()
    p = torch.softmax(logits, -1)
    return {m: float(p[t]) for m, t in first.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="990030-990049")
    ap.add_argument("--variants", default="R1,R2,R0,R4", help="R1 and R2 are the asked-for ones; R0 and R4 are references")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args(argv)
    lo, hi = (int(x) for x in args.seeds.split("-"))
    seeds = list(range(lo, hi + 1))
    assert all(s in DEV_SEEDS and s not in SEEDS_009_USED for s in seeds), "dev seeds only, none that 009 used"
    variants = [v for v in args.variants.split(",") if v]
    Path(args.out).mkdir(parents=True, exist_ok=True)

    status("probe 1/3 loading", MODEL_ID)
    with tqdm(total=1, desc="model load", unit="model", dynamic_ncols=True) as bar:
        model, tok = load_model()
        bar.update(1)
    first = {m: tok(m, add_special_tokens=False)["input_ids"][0] for m in MOVES}
    assert len(set(first.values())) == len(MOVES), first
    critter = Diag2Critter(model, tok)
    base = read_system_prompt("stakes")

    out: dict = {}
    total = len(variants) * len(CASES) * len(seeds)
    status("probe 2/3 sampling", f"{len(variants)} variants x {len(CASES)} cases x {len(seeds)} seeds = {total} turn-1 calls")
    bar = tqdm(total=total, desc="probe", unit="call", dynamic_ncols=True)
    for v in variants:
        system, window = variant_system(v, base)
        move_first = VARIANTS[v][0] is None
        out[v] = {"diary_window": window, "move_first": move_first, "cases": {}}
        for case in CASES:
            rows = []
            for s in seeds:
                text = turn1_text(s, window, case)
                if text is None:
                    bar.update(1)
                    continue
                prompt_ids = critter._encode(system, text)
                if move_first:
                    prefix, reply = FORCED_PREFIX, None
                else:
                    reply = critter._decode(critter._generate_ids(prompt_ids, turn_seed(s, 1, 0), False))
                    m = MOVE_KEY.search(reply)
                    prefix = reply[:m.end()] if m else None
                row = {"seed": s, "reply": reply}
                if prefix is not None:
                    row["p"] = move_distribution(model, tok, prompt_ids, prefix, first)
                    if reply is not None:
                        rest = reply[len(prefix):]
                        row["sampled_move"] = next((mv for mv in MOVES if rest.startswith(mv)), None)
                rows.append(row)
                bar.update(1)
            scored = [r for r in rows if "p" in r]
            mean = {m: sum(r["p"][m] for r in scored) / len(scored) for m in MOVES} if scored else {}
            argmax = {m: sum(max(r["p"], key=r["p"].get) == m for r in scored) for m in MOVES}
            sampled = {m: sum(r.get("sampled_move") == m for r in scored) for m in MOVES}
            out[v]["cases"][case] = {"n": len(rows), "n_scored": len(scored), "mean_prob": mean, "argmax_count": argmax,
                                     "sampled_move_count": sampled,
                                     "mean_mass_on_the_six": sum(sum(r["p"].values()) for r in scored) / max(1, len(scored)),
                                     "per_seed": rows}
            status("probe", f"{v} {case:10s} n={len(scored)}/{len(seeds)}: mean P " + ", ".join(f"{m} {mean.get(m, float('nan')):.3f}" for m in MOVES)
                   + " | argmax " + json.dumps({m: c for m, c in argmax.items() if c}))
        (Path(args.out) / "probe_turn1.json").write_text(json.dumps({"model": MODEL_ID, "seeds": seeds, "variants": out}, indent=1), encoding="utf-8")
    bar.close()
    status("probe 3/3 done", str(Path(args.out) / "probe_turn1.json"))


if __name__ == "__main__":
    main()
