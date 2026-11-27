"""Job 011: reason-first replies and a shorter diary window for the Qwen critter, stakes condition, dev seeds.

    python arm2/diag2.py                      (from the repo root, Lobster-Lab venv, HF_HOME set)
    python arm2/diag2.py --variants R1 --seeds 990006 --max-turns 3 --out <dir>   (dry run)

Every variant uses the current stakes prompt plus job 009's variant I text (the "Your move" block). They differ only
in the Reply block (key order, how the diary is described) and the diary window:

  R0  variant I as 009 ran it: keys diary, look, move; window 15 (control)
  R1  R0 with the diary described as "what you see and what you plan, written before you choose your move"; window 15
  R2  R1 with the window at 5
  R3  R1 with the window at 3
  R4  the current key order (move, look, diary) with the window at 5

The window is changed here by patching world.observe.DIARY_SHOWN for the length of each episode (restored after),
and the system prompt's "its last 15 entries" is rewritten to match. prompts/ and world/ are not edited.
Variant text lives under M:\\Projects\\Lobster-Lab\\runs\\arm2\\diag2\\variants. Dev seeds only. No check-in question.
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

from arm2.diag_replay import episode_metrics, replay
from arm2.qwen_critter import MODEL_ID, QwenCritter, load_model, read_system_prompt
from world import observe
from world.episode import run_episode
from world.log import code_version, read_log

DEV_SEEDS = range(990000, 990200)
SEEDS_009_USED = set(range(990000, 990006)) | set(range(990010, 990030))  # episodes 990000, 990003-5; probes 990010-990029
DEFAULT_SEEDS = (990006, 990007, 990008, 990009)
OUT_DEFAULT = Path(r"M:\Projects\Lobster-Lab\runs\arm2\diag2")
EXPECTED_HF_HOME = r"M:\Projects\Lobster-Lab\hf_home"
VARIANT_DIR = OUT_DEFAULT / "variants"
ORIGINAL_REPLY_BLOCK_START = "Reply with one JSON object and nothing else:"
BASE_WINDOW = 15  # what prompts/critter_stakes.txt and world/observe.py say
BASE_WINDOW_TEXT = "its last 15 entries"

# name -> (reply block file, or None for the prompt's own block; diary window)
VARIANTS = {
    "R0": ("R0_reply_block.txt", 15),
    "R1": ("R1_reply_block.txt", 15),
    "R2": ("R1_reply_block.txt", 5),
    "R3": ("R1_reply_block.txt", 3),
    "R4": (None, 5),
}
ORDER = tuple(VARIANTS)


def build_system(base: str, insert: str, reply_block: str | None, window: int) -> str:
    """The stakes prompt with the Your move block before the Reply block, an optional replacement Reply block,
    and the diary window named in the prompt matched to the window actually shown."""
    i = base.index(ORIGINAL_REPLY_BLOCK_START)
    system = base[:i] + insert + (reply_block if reply_block is not None else base[i:])
    if window != BASE_WINDOW:
        assert BASE_WINDOW_TEXT in system, "prompt no longer says 'its last 15 entries'"
        system = system.replace(BASE_WINDOW_TEXT, f"its last {window} entries")
    return system


def variant_system(variant: str, base: str | None = None) -> tuple[str, int]:
    block_file, window = VARIANTS[variant]
    insert = (VARIANT_DIR / "Insert.txt").read_text(encoding="utf-8")
    block = (VARIANT_DIR / block_file).read_text(encoding="utf-8") if block_file else None
    return build_system(base if base is not None else read_system_prompt("stakes"), insert, block, window), window


class window_shown:
    """Patch world.observe.DIARY_SHOWN (read by observe.build, render_text and env._obs at call time), then restore it."""

    def __init__(self, n: int):
        self.n = n

    def __enter__(self):
        self.prev = observe.DIARY_SHOWN
        observe.DIARY_SHOWN = self.n

    def __exit__(self, *exc):
        observe.DIARY_SHOWN = self.prev


class Diag2Critter(QwenCritter):
    """QwenCritter whose system prompt is a diag2 variant. Sampling is exactly QwenCritter's."""

    def __init__(self, *a, variant: str = "R0", **k):
        super().__init__(*a, **k)
        self.variant = variant

    def begin_episode(self, seed, condition, **k):
        super().begin_episode(seed, condition, **k)
        self._system, self.window = variant_system(self.variant, self._system)

    def sampling_settings(self) -> dict:
        out = super().sampling_settings()
        out["variant"] = getattr(self, "variant", None)
        return out


# ---------------------------------------------------------------- extra metrics
def diary_repeat_stats(rows: list[dict]) -> tuple[int, int]:
    """(lines that repeat an earlier line of the same episode word for word, lines counted)."""
    seen, repeats, n = set(), 0, 0
    for r in rows:
        d = r.get("diary")
        if not isinstance(d, str) or not d.strip():
            continue
        key = " ".join(d.split())
        n += 1
        repeats += key in seen
        seen.add(key)
    return repeats, n


def extra_metrics(rows: list[dict]) -> dict:
    rep, n = diary_repeat_stats(rows)
    return {"eats_on_empty_cells": sum(r["move"] == "eat" and r["own_cell"] != "food" for r in rows),
            "diary_lines": n, "diary_repeats": rep}


# ---------------------------------------------------------------- running
def status(stage: str, msg: str):
    tqdm.write(f"[{time.strftime('%H:%M:%S')}] {stage}: {msg}")
    sys.stdout.flush()


def run_one(critter: Diag2Critter, variant: str, seed: int, out: Path, max_turns: int | None, version: str, desc: str) -> dict:
    key = f"{variant}_{seed}"
    log_path = out / "episodes" / f"{key}.jsonl.gz"
    critter.variant = variant
    window = VARIANTS[variant][1]
    t0 = time.perf_counter()
    with window_shown(window):
        critter.begin_episode(seed, "stakes", sidecar_path=out / "episodes" / f"{key}.sidecar.jsonl", desc=desc,
                              total_turns=max_turns or 48)
        critter._write_sidecar({"type": "variant", "variant": variant, "diary_window": window, "sampling": critter.sampling_settings()})
        try:
            run_episode(critter, condition="stakes", seed=seed, log_path=log_path, arm="arm2-diag2",
                        model=critter.name, max_turns=max_turns, version=version)
        finally:
            critter.end_episode()
    wall = time.perf_counter() - t0
    header, turns, end = read_log(log_path)
    rows = replay(log_path)
    m = episode_metrics(rows, turns, end)
    m.update(extra_metrics(rows))
    m.update(variant=variant, seed=seed, diary_window=window, wall_s=round(wall, 1), log=str(log_path))
    return m


def line(m: dict) -> str:
    return (f"{m['variant']} {m['seed']}: {m['turns']} turns, food {m['food_eaten']}, "
            f"{'fainted t%d' % m['faint_turn'] if m['fainted'] else 'survived'}, cells {m['distinct_cells']}, "
            f"moves {m['moves']}, F in shown {m['turns_F_in_shown_region']}/{m['turns']}, "
            f"on food {m['turns_standing_on_food']} ate {m['ate_when_on_food']}, eats on empty {m['eats_on_empty_cells']}, "
            f"valid {m['valid_first_try']}/{m['turns']}, repeats {m['diary_repeats']}/{m['diary_lines']}, {m['wall_s'] / 60:.1f} min")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--variants", default=",".join(ORDER))
    ap.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)))
    ap.add_argument("--max-turns", type=int, default=None, help="cap episode length (dry runs only)")
    ap.add_argument("--resume", action="store_true", help="skip (variant, seed) pairs already in diag2_results.json")
    args = ap.parse_args(argv)
    out = Path(args.out)
    (out / "episodes").mkdir(parents=True, exist_ok=True)
    assert os.environ.get("HF_HOME") == EXPECTED_HF_HOME, f"HF_HOME must be {EXPECTED_HF_HOME}, got {os.environ.get('HF_HOME')}"
    seeds = [int(s) for s in args.seeds.split(",")]
    assert all(s in DEV_SEEDS and s not in SEEDS_009_USED for s in seeds), "dev seeds 990006 to 990199 only, none that 009 used"
    variants = [v for v in args.variants.split(",") if v]
    assert all(v in VARIANTS for v in variants)
    version = code_version()
    t_start = time.perf_counter()
    results_path = out / "diag2_results.json"
    results: list[dict] = []
    if args.resume and results_path.exists():
        results = json.loads(results_path.read_text(encoding="utf-8"))["episodes"]
    done = {(m["variant"], m["seed"]) for m in results}

    VARIANT_DIR.mkdir(parents=True, exist_ok=True)
    for v in variants:  # the assembled prompts, for the record
        system, window = variant_system(v)
        (VARIANT_DIR / f"{v}_system_prompt.txt").write_text(system, encoding="utf-8", newline="")

    status("stage 1/3 loading", f"{MODEL_ID} in 4-bit NF4 from {os.environ['HF_HOME']}, offline")
    with tqdm(total=1, desc="model load", unit="model", dynamic_ncols=True) as bar:
        model, tok = load_model()
        bar.update(1)
    critter = Diag2Critter(model, tok)
    status("stage 1/3 loading", f"done, {torch.cuda.memory_allocated() / 2**30:.2f} GiB allocated")

    planned = [(v, s) for v in variants for s in seeds if (v, s) not in done]
    status("stage 2/3 episodes", f"{len(planned)} episodes ({','.join(variants)} x seeds {seeds}), stakes, cap {args.max_turns or 48} turns"
                                 + (f", {len(done)} already done" if done else ""))
    outer = tqdm(total=len(planned), desc="all episodes", unit="ep", dynamic_ncols=True, position=1, leave=True)
    for v, s in planned:
        m = run_one(critter, v, s, out, args.max_turns, version, desc=f"variant {v} seed {s}")
        results.append(m)
        results_path.write_text(json.dumps({"model": MODEL_ID, "code_version": version, "episodes": results}, indent=1), encoding="utf-8")
        outer.update(1)
        status("episode done", line(m))
    outer.close()
    status("stage 3/3 summary", f"{results_path}, {(time.perf_counter() - t_start) / 60:.1f} min total")
    print("\nvariant seed turns faint food cells F_shown on_food ate empty_eats valid repeats")
    for m in results:
        print(f"{m['variant']:7s} {m['seed']} {m['turns']:5d} {str(m['faint_turn'] or '-'):>5s} {m['food_eaten']:4d} {m['distinct_cells']:5d} "
              f"{m['turns_F_in_shown_region']:7d} {m['turns_standing_on_food']:7d} {m['ate_when_on_food']:3d} {m['eats_on_empty_cells']:5d} "
              f"{m['valid_first_try']:5d} {m['diary_repeats']}/{m['diary_lines']}")


if __name__ == "__main__":
    main()
