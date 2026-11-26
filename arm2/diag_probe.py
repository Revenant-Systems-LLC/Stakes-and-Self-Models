"""Job 009 extra probe: how much probability does Qwen put on each move word at the start of its reply?

    python arm2/diag_probe.py [--seeds 990010-990029] [--out <dir>]

For turn 1 of each dev seed (stakes), the prompt is the system prompt (plus the variant's change) and
the assistant reply is forced to begin  {"move": "  . One forward pass gives the next-token distribution;
the six move words are compared on their first token. No sampling, no episode. Dev seeds only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("HF_HOME", r"M:\Projects\Lobster-Lab\hf_home")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
from tqdm import tqdm

from arm2.diag import OUT_DEFAULT, VARIANT_DIR, strip_map_dividers  # noqa: F401
from arm2.qwen_critter import MODEL_ID, load_model, read_system_prompt
from world.env import MOVES, CritterWorld

PREFIX = '{"move": "'


def synthetic_cases() -> dict[str, str]:
    """Hand-made turns (energy 10, empty diary, region 4 shown): food next to the critter in each direction, food underfoot, nothing."""
    from world import observe

    def turn(cells: dict[tuple[int, int], str], own: str = "nothing", diary_lines: int = 0) -> str:
        rows = [["."] * 9 for _ in range(9)]
        for (r, c), ch in cells.items():
            rows[r][c] = ch
        rows[4][4] = "@"
        obs = {"turn": 5, "of_turns": 48, "window": ["".join(r) for r in rows], "own_cell": own,
               "energy": 10, "health": 10,
               "diary": [{"turn": 5 - diary_lines + i, "text": "Heading south to look for food."} for i in range(diary_lines)]}
        return observe.render_text(obs)

    return {"F north": turn({(3, 4): "F"}), "F south": turn({(5, 4): "F"}), "F east": turn({(4, 5): "F"}),
            "F west": turn({(4, 3): "F"}), "on food": turn({}, own="food"), "empty map": turn({}),
            "on food, 4 south-diary lines": turn({}, own="food", diary_lines=4),
            "on food, 4 south-diary lines (turn 5 so all shown)": turn({}, own="food", diary_lines=4),
            "F north, 4 south-diary lines": turn({(3, 4): "F"}, diary_lines=4)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="990010-990029")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args(argv)
    lo, hi = (int(x) for x in args.seeds.split("-"))
    seeds = list(range(lo, hi + 1))
    assert all(990000 <= s <= 990199 for s in seeds), "dev seeds only"

    print(f"[{time.strftime('%H:%M:%S')}] loading {MODEL_ID}", flush=True)
    model, tok = load_model()
    first = {m: tok(m, add_special_tokens=False)["input_ids"][0] for m in MOVES}
    assert len(set(first.values())) == len(MOVES), first
    print(f"[{time.strftime('%H:%M:%S')}] first tokens {first}", flush=True)
    suffix_c = (VARIANT_DIR / "C_system_suffix.txt").read_text(encoding="utf-8")
    sys_a = read_system_prompt("stakes")
    configs = {"A": (sys_a, None), "C": (sys_a + suffix_c, None)}
    out = {}
    for name, (system, _) in configs.items():
        probs = []
        for s in tqdm(seeds, desc=f"probe {name}", unit="seed", dynamic_ncols=True):
            env = CritterWorld("stakes")
            env.reset(seed=s)
            _, text = env.critter_view()
            msgs = [{"role": "system", "content": system}, {"role": "user", "content": text}]
            ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True)["input_ids"][0].tolist()
            ids += tok(PREFIX, add_special_tokens=False)["input_ids"]
            with torch.no_grad():
                logits = model(input_ids=torch.tensor([ids], device=model.device)).logits[0, -1].float()
            p = torch.softmax(logits, -1)
            probs.append({m: float(p[t]) for m, t in first.items()})
        mean = {m: sum(r[m] for r in probs) / len(probs) for m in MOVES}
        argmax = {m: sum(max(r, key=r.get) == m for r in probs) for m in MOVES}
        synth = {}
        for case, text in synthetic_cases().items():
            msgs = [{"role": "system", "content": system}, {"role": "user", "content": text}]
            ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True)["input_ids"][0].tolist()
            ids += tok(PREFIX, add_special_tokens=False)["input_ids"]
            with torch.no_grad():
                p = torch.softmax(model(input_ids=torch.tensor([ids], device=model.device)).logits[0, -1].float(), -1)
            synth[case] = {m: round(float(p[t]), 3) for m, t in first.items()}
            print(f"[{time.strftime('%H:%M:%S')}] {name} synthetic {case}: " + ", ".join(f"{m} {v:.3f}" for m, v in synth[case].items()), flush=True)
        out[name] = {"synthetic": synth, "mean_prob": mean, "argmax_count": argmax, "per_seed": dict(zip(map(str, seeds), probs))}
        print(f"[{time.strftime('%H:%M:%S')}] {name}: mean P " + ", ".join(f"{m} {mean[m]:.3f}" for m in MOVES)
              + " | argmax counts " + json.dumps(argmax), flush=True)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "probe_move_prior.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
