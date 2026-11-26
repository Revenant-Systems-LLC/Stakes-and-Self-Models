"""Arm 2 smoke test: does the local Qwen critter play whole episodes, and does the hook do what it should?

    python -m arm2.smoke                      (from the repo root, Lobster-Lab venv)
    python -m arm2.smoke --max-turns 3 --out M:\\Projects\\Lobster-Lab\\runs\\arm2\\_dryrun

Stages: 1 prompt length check, 2 model load and warm-up, 3 four unsteered episodes
(dev seeds 990000 and 990001, both conditions) with layer norms measured on them,
4 determinism check, 5 hook check (stakes episode on seed 990002, random unit vector,
layer 18, strength 4, "generated" mode, every turn), 6 writing results.

Dev seeds only (990000 to 990199). No check-in question is ever asked.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch
from tqdm import tqdm

from arm2 import steering
from arm2.qwen_critter import MODEL_ID, PROMPT_FILES, QwenCritter, load_model, read_system_prompt
from world.episode import run_episode
from world.log import code_version, read_log

DEV_SEEDS = range(990000, 990200)
NORM_SEEDS = (990000, 990001)
HOOK_SEED = 990002
HOOK_LAYER, HOOK_STRENGTH, HOOK_MODE = 18, 4, "generated"
VECTOR_SEED = 20261125
EXPECTED_HF_HOME = r"M:\Projects\Lobster-Lab\hf_home"
N_STAGES = 6


def status(stage: int, name: str, msg: str):
    tqdm.write(f"[{time.strftime('%H:%M:%S')}] stage {stage}/{N_STAGES} {name}: {msg}")
    sys.stdout.flush()


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def episode_report(log_path: Path, calls: list[dict], summary: dict, wall_s: float) -> dict:
    _, turns, _ = read_log(log_path)
    by_turn: dict[int, float] = {}
    for c in calls:
        by_turn[c["turn"]] = by_turn.get(c["turn"], 0.0) + c["seconds"]
    secs = list(by_turn.values())
    return {
        "turns": summary["turns"], "fainted": summary["fainted"], "food": summary["food_eaten"],
        "thorns": summary["thorns_hit"],
        "valid_first_try": sum(t["reply_valid"] and len(t["raw_reply"]) == 1 for t in turns),
        "valid_after_retry": sum(t["reply_valid"] and len(t["raw_reply"]) == 2 for t in turns),
        "invalid_turns": sum(not t["reply_valid"] for t in turns),
        "model_calls": len(calls),
        "fenced_replies": sum(c["fenced"] for c in calls),
        "mean_s_per_turn": mean(secs), "max_s_per_turn": max(secs) if secs else None,
        "mean_tokens_out": mean(c["tokens_out"] for c in calls), "mean_tokens_in": mean(c["tokens_in"] for c in calls),
        "hit_120": sum(c["hit_cap"] for c in calls), "wall_s": round(wall_s, 1),
        "steered_calls": sum(c["steered"] for c in calls),
    }


def raw_samples(log_path: Path) -> list[dict]:
    """Three raw first-attempt replies, evenly spaced through the episode (first, middle, last turn)."""
    _, turns, _ = read_log(log_path)
    return [{"turn": turns[i]["turn"], "valid": turns[i]["reply_valid"], "raw_reply": turns[i]["raw_reply"][0]}
            for i in pick(len(turns), 3)]


def pick(n: int, k: int) -> list[int]:
    """k evenly spaced indices out of n."""
    if n <= k:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(steering.RUNS_DIR))
    ap.add_argument("--max-turns", type=int, default=None, help="cap episode length (dry runs only)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    assert os.environ.get("HF_HOME") == EXPECTED_HF_HOME, f"HF_HOME must be {EXPECTED_HF_HOME}, got {os.environ.get('HF_HOME')}"
    assert all(s in DEV_SEEDS for s in (*NORM_SEEDS, HOOK_SEED)), "dev seeds only"
    version = code_version()
    report: dict = {"model": MODEL_ID, "code_version": version, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "max_turns_cap": args.max_turns, "out": str(out)}
    t_start = time.perf_counter()

    # ---------------------------------------------------------------- 1 prompt length
    status(1, "prompt check", "token counts of both system prompts with the Qwen tokenizer")
    from transformers import AutoTokenizer
    tok0 = AutoTokenizer.from_pretrained(MODEL_ID)
    counts = {c: len(tok0(read_system_prompt(c), add_special_tokens=False)["input_ids"]) for c in PROMPT_FILES}
    a, b = counts["stakes"], counts["no_stakes"]
    gap_larger, gap_smaller = abs(a - b) / max(a, b) * 100, abs(a - b) / min(a, b) * 100
    report["prompt_tokens"] = {**counts, "gap_pct_of_larger": round(gap_larger, 2),
                               "gap_pct_of_smaller": round(gap_smaller, 2), "within_10pct": max(gap_larger, gap_smaller) <= 10}
    status(1, "prompt check", f"stakes {a} tokens, no_stakes {b} tokens, gap {gap_larger:.1f}% of the larger "
                              f"({gap_smaller:.1f}% of the smaller), within 10%: {report['prompt_tokens']['within_10pct']}")

    # ---------------------------------------------------------------- 2 load and warm-up
    status(2, "loading", f"{MODEL_ID} in 4-bit NF4 (float16 compute) from {os.environ['HF_HOME']}, offline")
    t0 = time.perf_counter()
    with tqdm(total=1, desc="model load", unit="model", dynamic_ncols=True) as bar:
        model, tok = load_model()
        bar.update(1)
    torch.cuda.reset_peak_memory_stats()
    critter = QwenCritter(model, tok)
    critter.keep_trace = True
    layers = model.model.layers
    report["load_s"] = round(time.perf_counter() - t0, 1)
    report["n_layers"], report["hidden_size"] = len(layers), model.config.hidden_size
    report["sampling"] = critter.sampling_settings()
    status(2, "loading", f"done in {report['load_s']} s, {len(layers)} layers, width {model.config.hidden_size}, "
                         f"{torch.cuda.memory_allocated() / 2**30:.2f} GiB allocated")
    status(2, "warm-up", "one throwaway critter turn on seed 990000 (not logged)")
    from world.env import CritterWorld
    env = CritterWorld("stakes")
    env.reset(seed=NORM_SEEDS[0])
    _, text = env.critter_view()
    ids = critter._encode(read_system_prompt("stakes"), text)
    t0 = time.perf_counter()
    with tqdm(total=2, desc="warm-up", unit="gen", dynamic_ncols=True) as bar:
        for k in range(2):
            critter._generate_ids(ids, k, False)
            bar.update(1)
    report["warmup_s_per_gen"] = round((time.perf_counter() - t0) / 2, 2)
    status(2, "warm-up", f"{report['warmup_s_per_gen']} s per generation")

    # ---------------------------------------------------------------- 3 unsteered episodes + layer norms
    plan = [(s, c) for s in NORM_SEEDS for c in ("stakes", "no_stakes")]
    status(3, "episodes", f"{len(plan)} unsteered episodes, residual norms recorded on all {len(layers)} layers")
    episodes, ep_dir, traces, ep_meta = {}, out / "episodes", {}, []
    stakes_turns: dict[int, int] = {}
    recorder = steering.NormRecorder(layers)
    critter.recorder = recorder
    with recorder:
        for k, (seed, cond) in enumerate(plan, 1):
            max_turns = args.max_turns if cond == "stakes" else stakes_turns[seed]
            key = f"{seed}_{cond}"
            log_path = ep_dir / f"{key}.jsonl.gz"
            critter.begin_episode(seed, cond, sidecar_path=ep_dir / f"{key}.sidecar.jsonl",
                                  desc=f"episode {k} of {len(plan)} ({cond} {seed})", total_turns=max_turns or 48)
            t0 = time.perf_counter()
            try:
                summary = run_episode(critter, condition=cond, seed=seed, log_path=log_path, arm="arm2-dev",
                                      model=critter.name, max_turns=max_turns, version=version)
            finally:
                calls = list(critter.calls)
                critter.end_episode()
            wall = time.perf_counter() - t0
            if cond == "stakes":
                stakes_turns[seed] = summary["turns"]
            episodes[key] = episode_report(log_path, calls, summary, wall)
            episodes[key]["steering"] = None
            traces[key] = list(critter.trace)
            ep_meta.append({"seed": seed, "condition": cond, "turns": summary["turns"]})
            status(3, "episodes", f"{key}: {summary['turns']} turns, fainted={summary['fainted']}, "
                                  f"{episodes[key]['mean_s_per_turn']:.1f} s/turn, {wall / 60:.1f} min")
    critter.recorder = None
    norms_path = out / "layer_norms.json"
    norms = steering.layer_norms(recorder, norms_path, seeds=NORM_SEEDS, conditions=("stakes", "no_stakes"),
                                 episodes=ep_meta, model_name=MODEL_ID)
    norm_stats = recorder.stats()
    report["layer_norms"] = {"path": str(norms_path), "turns": sum(e["turns"] for e in ep_meta),
                             "positions": norm_stats["positions"], "seeds": list(NORM_SEEDS),
                             "layers": {L: {k: v for k, v in norm_stats["layers"][L].items()} for L in (10, 14, 18, 22)}}
    status(3, "layer norms", f"saved {norms_path} (layer 14 {norms[14]:.1f}, 18 {norms[18]:.1f}, 22 {norms[22]:.1f}; "
                             f"{norm_stats['positions']} positions)")

    # ---------------------------------------------------------------- 4 determinism
    tr = traces[f"{NORM_SEEDS[0]}_stakes"]
    idx = sorted({0, len(tr) // 2, len(tr) - 1})
    status(4, "determinism", f"regenerating {len(idx)} stored turns from seed {NORM_SEEDS[0]} with the same seeds")
    same = 0
    for i in tqdm(idx, desc="determinism", unit="turn", dynamic_ncols=True):
        again = critter.generate_from_ids(tr[i]["prompt_ids"], tr[i]["seed"], False)
        same += again == tr[i]["reply"]
    report["determinism"] = {"regenerated": len(idx), "identical": same}
    status(4, "determinism", f"{same} of {len(idx)} identical")

    # ---------------------------------------------------------------- 5 hook check
    status(5, "hook check", f"stakes episode on seed {HOOK_SEED}: random unit vector (seed {VECTOR_SEED}), layer {HOOK_LAYER}, "
                            f"strength {HOOK_STRENGTH}, mode {HOOK_MODE}, every turn")
    vec_path = out / "vectors" / f"random_seed{VECTOR_SEED}.npy"
    vec_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(vec_path, steering.random_unit_vector(VECTOR_SEED, model.config.hidden_size))
    vec = steering.load_vector(vec_path, dim=model.config.hidden_size)
    critter.layer_norms = steering.load_layer_norms(norms_path)
    spec = steering.SteeringSpec(HOOK_LAYER, vec, HOOK_STRENGTH, mode=HOOK_MODE, turns=None)
    critter.set_steering(spec)
    desc = critter.steering_description()
    key = f"{HOOK_SEED}_stakes_steered"
    log_path = ep_dir / f"{key}.jsonl.gz"
    critter.begin_episode(HOOK_SEED, "stakes", sidecar_path=ep_dir / f"{key}.sidecar.jsonl",
                          desc=f"hook episode ({HOOK_SEED} stakes, L{HOOK_LAYER} s{HOOK_STRENGTH})",
                          total_turns=args.max_turns or 48)
    t0 = time.perf_counter()
    try:
        summary = run_episode(critter, condition="stakes", seed=HOOK_SEED, log_path=log_path, arm="arm2-dev",
                              model=critter.name, max_turns=args.max_turns, version=version)
    finally:
        calls = list(critter.calls)
        critter.end_episode()
    episodes[key] = episode_report(log_path, calls, summary, time.perf_counter() - t0)
    episodes[key]["steering"] = desc
    trace = list(critter.trace)
    critter.set_steering(None)

    intended = desc["magnitude"]
    delta = torch.from_numpy(vec).to(model.device) * intended
    measured = []
    for i in tqdm(pick(len(trace), 6), desc="measure residual change", unit="turn", dynamic_ncols=True):
        e = trace[i]
        reply_ids = e["reply_ids"][:-1] if e["reply_ids"] and e["reply_ids"][-1] in critter._eos_ids() else e["reply_ids"]
        full = torch.tensor([e["prompt_ids"] + reply_ids], device=model.device)
        m = steering.measure_change(model, HOOK_LAYER, len(e["prompt_ids"]), full, delta, HOOK_MODE)
        m["turn"] = e["turn"]
        measured.append(m)
    n_cmp = min(len(trace), 12)
    differ, examples = 0, []
    for i in tqdm(pick(len(trace), n_cmp), desc="same seeded turn, unsteered", unit="turn", dynamic_ncols=True):
        e = trace[i]
        plain = critter.generate_from_ids(e["prompt_ids"], e["seed"], False)
        if plain != e["reply"]:
            differ += 1
            if len(examples) < 2:
                examples.append({"turn": e["turn"], "attempt": e["attempt"], "steered": e["reply"], "unsteered": plain})
    report["hook_check"] = {
        "steering": desc, "vector_file": str(vec_path), "intended_norm": intended,
        "residual_change": measured,
        "measured_over_intended_mean": mean(m["measured_over_intended"] for m in measured),
        "prompt_positions_max_change": max(m["unsteered_positions_max_change"] for m in measured),
        "cosine_with_vector_mean": mean(m["cosine_with_vector_mean"] for m in measured),
        "intended_over_residual_norm": intended / mean(m["residual_norm_at_steered_positions_mean"] for m in measured),
        "same_seeded_turns_compared": n_cmp, "replies_that_differ": differ, "examples": examples,
    }
    status(5, "hook check", f"measured/intended {report['hook_check']['measured_over_intended_mean']:.4f}, "
                            f"{differ} of {n_cmp} seeded turns differ from unsteered")

    # ---------------------------------------------------------------- 6 results
    status(6, "writing results", f"{out / 'smoke_report.json'}")
    report["episodes"] = episodes
    report["raw_samples"] = {c: raw_samples(ep_dir / f"{NORM_SEEDS[0]}_{c}.jsonl.gz") for c in ("stakes", "no_stakes")}
    report["peak_vram_allocated_GiB"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
    report["peak_vram_reserved_GiB"] = round(torch.cuda.max_memory_reserved() / 2**30, 2)
    report["total_s"] = round(time.perf_counter() - t_start)
    (out / "smoke_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    print("\n==== SMOKE SUMMARY ====")
    print(json.dumps({k: report[k] for k in ("prompt_tokens", "determinism", "peak_vram_allocated_GiB",
                                             "peak_vram_reserved_GiB", "total_s")}, indent=1))
    print(f"{'episode':30s} turns faint food thorn first retry invalid fenced  s/turn  max  tok_out hit120")
    for k, e in episodes.items():
        print(f"{k:30s} {e['turns']:5d} {str(e['fainted'])[0]:>5s} {e['food']:4d} {e['thorns']:5d} {e['valid_first_try']:5d} "
              f"{e['valid_after_retry']:5d} {e['invalid_turns']:7d} {e['fenced_replies']:6d} {e['mean_s_per_turn']:7.1f} "
              f"{e['max_s_per_turn']:4.1f} {e['mean_tokens_out']:7.1f} {e['hit_120']:6d}")
    print(json.dumps(report["hook_check"], indent=1, ensure_ascii=False))
    for cond, rows in report["raw_samples"].items():
        for r in rows:
            print(f"RAW {cond} t{r['turn']} valid={r['valid']}: {r['raw_reply']!r}")


if __name__ == "__main__":
    main()
