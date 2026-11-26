"""Job 009 step 2 and 3: prompt and sampling variants for the Qwen critter, stakes condition, dev seeds.

    python arm2/diag.py                      (from the repo root, Lobster-Lab venv, HF_HOME set)
    python arm2/diag.py --variants A,B --seeds 990003 --max-turns 3 --out <dir>   (dry run)

Variants (all stakes, one episode per seed, 48-turn cap):
  A  current prompt, default sampling (baseline; identical to arm2.qwen_critter)
  B  current prompt, greedy decoding (do_sample=False; the model's repetition penalty stays)
  C  current prompt plus the worked example in diag/variants/C_system_suffix.txt appended to the system prompt
  D  current prompt, turn text gains one line naming the region shown in detail (diagnosis only: the
     preregistered attention swap depends on the text never saying this)
  E  only if A to D all eat nothing: turn text with the map's pipes and dividers removed
  F  (added after A to E all failed) Reply block of the system prompt reordered: diary, look, move
  G  F plus the worked example, its reply in the same key order (only runs if F eats nothing)
  H  one added paragraph before the Reply block: read "Your cell" first, eat if food, write each diary line fresh
  I  H with the Reply block of F (diary, look, move)
  J  H plus two sentences on moving: walk to F when seen, otherwise toward the most ?, change direction at #
  K  J with the Reply block of F

Nothing here changes prompts/ or world/. Dev seeds only (990000 to 990199). No check-in question is asked.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("HF_HOME", r"M:\Projects\Lobster-Lab\hf_home")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
from tqdm import tqdm

import world.episode as episode_mod
from arm2.diag_replay import episode_metrics, replay
from arm2.qwen_critter import MODEL_ID, QwenCritter, load_model
from world.env import CritterWorld
from world.episode import run_episode
from world.log import code_version, read_log

DEV_SEEDS = range(990000, 990200)
DEFAULT_SEEDS = (990003, 990004, 990005)
OUT_DEFAULT = Path(r"M:\Projects\Lobster-Lab\runs\arm2\diag")
EXPECTED_HF_HOME = r"M:\Projects\Lobster-Lab\hf_home"
VARIANT_DIR = OUT_DEFAULT / "variants"
ORDER = ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K")
ORIGINAL_REPLY_BLOCK_START = "Reply with one JSON object and nothing else:"


class TrackingWorld(CritterWorld):
    """CritterWorld that remembers the newest instance, so variant D can read the region actually shown."""

    current: "TrackingWorld | None" = None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        TrackingWorld.current = self


def strip_map_dividers(text: str) -> str:
    """Variant E: delete the two divider lines and the pipes between regions."""
    lines = [ln for ln in text.split("\n") if not ln.startswith("------+")]
    return "\n".join(ln.replace(" | ", " ") if " | " in ln else ln for ln in lines)


class DiagCritter(QwenCritter):
    """QwenCritter with one variant switched on. With no variant it behaves exactly like QwenCritter."""

    def __init__(self, *a, variant: str = "A", **k):
        super().__init__(*a, **k)
        self.variant = variant
        self.set_variant(variant)

    def set_variant(self, variant: str):
        self.variant = variant
        read = lambda name: (VARIANT_DIR / name).read_text(encoding="utf-8")
        self.system_suffix = read("C_system_suffix.txt") if variant == "C" else read("G_system_suffix.txt") if variant == "G" else ""
        self.turn_line = read("D_turn_line.txt") if variant == "D" else ""
        self.reply_block = read("F_reply_block.txt") if variant in ("F", "G", "I", "K") else ""
        self.insert = read("H_insert.txt") if variant in ("H", "I") else read("J_insert.txt") if variant in ("J", "K") else ""

    def sampling_settings(self) -> dict:
        out = super().sampling_settings()
        out["variant"] = getattr(self, "variant", "A")
        if getattr(self, "variant", "A") == "B":
            out.update(do_sample=False, temperature=None, top_p=None, top_k=None)
        return out

    def _encode(self, system: str, user: str) -> list[int]:
        if self.reply_block or self.insert:
            i = system.index(ORIGINAL_REPLY_BLOCK_START)
            system = system[:i] + self.insert + (self.reply_block or system[i:])
        if self.system_suffix:
            system = system + self.system_suffix
        if self.variant == "D":
            region = TrackingWorld.current.shown_region
            user = user.replace("\nYour cell:", "\n" + self.turn_line.format(region=region) + "\nYour cell:", 1)
        elif self.variant == "E":
            user = strip_map_dividers(user)
        return super()._encode(system, user)

    @torch.no_grad()
    def _generate_ids(self, prompt_ids: list[int], seed: int, steer: bool) -> list[int]:
        if self.variant != "B":
            return super()._generate_ids(prompt_ids, seed, steer)
        assert not steer and self.recorder is None
        input_ids = torch.tensor([prompt_ids], device=self.model.device)
        torch.manual_seed(seed)
        out = self.model.generate(input_ids=input_ids, attention_mask=torch.ones_like(input_ids),
                                  max_new_tokens=self.max_new_tokens, pad_token_id=self.tok.pad_token_id,
                                  do_sample=False, temperature=None, top_p=None, top_k=None)
        return out[0, input_ids.shape[1]:].tolist()


def status(stage: str, msg: str):
    tqdm.write(f"[{time.strftime('%H:%M:%S')}] {stage}: {msg}")
    sys.stdout.flush()


def run_one(critter: DiagCritter, variant: str, seed: int, out: Path, max_turns: int | None, version: str, desc: str) -> dict:
    key = f"{variant}_{seed}"
    log_path = out / "episodes" / f"{key}.jsonl.gz"
    critter.set_variant(variant)
    critter.begin_episode(seed, "stakes", sidecar_path=out / "episodes" / f"{key}.sidecar.jsonl", desc=desc,
                          total_turns=max_turns or 48)
    critter._write_sidecar({"type": "variant", "variant": variant, "sampling": critter.sampling_settings()})
    t0 = time.perf_counter()
    try:
        summary = run_episode(critter, condition="stakes", seed=seed, log_path=log_path, arm="arm2-diag",
                              model=critter.name, max_turns=max_turns, version=version)
    finally:
        critter.end_episode()
    wall = time.perf_counter() - t0
    header, turns, end = read_log(log_path)
    rows = replay(log_path)
    m = episode_metrics(rows, turns, end)
    m.update(variant=variant, seed=seed, wall_s=round(wall, 1), log=str(log_path))
    return m


def line(m: dict) -> str:
    return (f"{m['variant']} {m['seed']}: {m['turns']} turns, food {m['food_eaten']}, "
            f"{'fainted t%d' % m['faint_turn'] if m['fainted'] else 'survived'}, cells {m['distinct_cells']}, "
            f"moves {m['moves']}, F in shown region {m['turns_F_in_shown_region']}/{m['turns']}, "
            f"on food {m['turns_standing_on_food']} ate {m['ate_when_on_food']}, valid {m['valid_first_try']}/{m['turns']}, "
            f"{m['wall_s'] / 60:.1f} min")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--variants", default="A,B,C,D", help="comma list; E runs automatically if A to D all eat nothing")
    ap.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)))
    ap.add_argument("--max-turns", type=int, default=None, help="cap episode length (dry runs only)")
    ap.add_argument("--no-e", action="store_true", help="never run variant E")
    ap.add_argument("--auto-g", action="store_true", help="run G after F if F ate nothing")
    args = ap.parse_args(argv)
    out = Path(args.out)
    (out / "episodes").mkdir(parents=True, exist_ok=True)
    assert os.environ.get("HF_HOME") == EXPECTED_HF_HOME, f"HF_HOME must be {EXPECTED_HF_HOME}, got {os.environ.get('HF_HOME')}"
    seeds = [int(s) for s in args.seeds.split(",")]
    assert all(s in DEV_SEEDS for s in seeds), "dev seeds only"
    variants = [v for v in args.variants.split(",") if v]
    assert all(v in ORDER for v in variants)
    episode_mod.CritterWorld = TrackingWorld
    version = code_version()
    t_start = time.perf_counter()

    status("stage 1/3 loading", f"{MODEL_ID} in 4-bit NF4 from {os.environ['HF_HOME']}, offline")
    with tqdm(total=1, desc="model load", unit="model", dynamic_ncols=True) as bar:
        model, tok = load_model()
        bar.update(1)
    critter = DiagCritter(model, tok)
    status("stage 1/3 loading", f"done, {torch.cuda.memory_allocated() / 2**30:.2f} GiB allocated")

    results: list[dict] = []
    planned = [(v, s) for v in variants for s in seeds]
    status("stage 2/3 episodes", f"{len(planned)} episodes ({','.join(variants)} x seeds {seeds}), stakes, "
                                 f"cap {args.max_turns or 48} turns; E only if A to D all eat nothing")
    outer = tqdm(total=len(planned), desc="all episodes", unit="ep", dynamic_ncols=True, position=1, leave=True)

    def save():
        (out / "diag_results.json").write_text(json.dumps({"model": MODEL_ID, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                           "code_version": version, "episodes": results}, indent=1), encoding="utf-8")

    def go(v: str, s: int):
        m = run_one(critter, v, s, out, args.max_turns, version, desc=f"variant {v} seed {s}")
        results.append(m)
        save()
        outer.update(1)
        status("episode done", line(m))

    for v, s in planned:
        go(v, s)

    ran_a_to_d = {v for v in variants} >= {"A", "B", "C", "D"}
    all_fail = ran_a_to_d and all(m["food_eaten"] == 0 for m in results if m["variant"] in "ABCD")
    if all_fail and not args.no_e and "E" not in variants:
        status("stage 2/3 episodes", "A to D all ate nothing: running E")
        outer.total += len(seeds)
        outer.refresh()
        for s in seeds:
            go("E", s)
    if args.auto_g and "F" in variants and "G" not in variants and all(m["food_eaten"] == 0 for m in results if m["variant"] == "F"):
        status("stage 2/3 episodes", "F ate nothing: running G")
        outer.total += len(seeds)
        outer.refresh()
        for s in seeds:
            go("G", s)
    if ran_a_to_d and not all_fail:
        status("stage 2/3 episodes", "at least one of A to D ate food: E not run")
    outer.close()

    status("stage 3/3 summary", f"{out / 'diag_results.json'}, {(time.perf_counter() - t_start) / 60:.1f} min total")
    print("\nvariant seed turns faint food cells  F_shown F_vis on_food ate  toward_F onto_F valid")
    for m in results:
        print(f"{m['variant']:7s} {m['seed']} {m['turns']:5d} {str(m['faint_turn'] or '-'):>5s} {m['food_eaten']:4d} {m['distinct_cells']:5d} "
              f"{m['turns_F_in_shown_region']:7d} {m['turns_F_visible_anywhere']:5d} {m['turns_standing_on_food']:7d} {m['ate_when_on_food']:3d} "
              f"{m['moved_toward_nearest_visible_F']:8d} {m['stepped_onto_visible_F']:6d} {m['valid_first_try']:5d}")


if __name__ == "__main__":
    main()
