"""Food-density check with the scripted GreedyAgent, stakes condition only.

Development seeds only (990000-990199); these never go into a pilot or
confirmatory run. A starting point for pilot tuning, not the tuned value: the
preregistration tunes density on pilot seeds with real critters.

    python -m world.run_density
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tqdm import tqdm

from world.agents import GreedyAgent, RandomAgent
from world.env import WorldConfig
from world.episode import run_episode
from world.log import code_version

DEV_SEEDS = range(990000, 990200)
DENSITIES = (0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18)
THORN_DENSITY = 0.08
RESPAWN = 8
TARGET_FAINT = 0.15
OUT = Path(__file__).resolve().parent / "_smoke_logs" / "density"


def sweep(agent_cls, cfg: WorldConfig, label: str, version: str) -> dict:
    rows = []
    for seed in tqdm(DEV_SEEDS, desc=label, unit="ep", leave=True):
        rows.append(run_episode(agent_cls(seed), condition="stakes", seed=seed, config=cfg, arm="density",
                                log_path=OUT / label / f"{seed}.jsonl.gz", version=version))
    n = len(rows)
    return {
        "faint": sum(r["fainted"] for r in rows) / n,
        "length": sum(r["turns"] for r in rows) / n,
        "food": sum(r["food_eaten"] for r in rows) / n,
        "thorns": sum(r["thorns_hit"] for r in rows) / n,
        "invalid": sum(r["invalid_turns"] for r in rows),
    }


def line(name, r):
    return f"| {name} | {r['faint']:.3f} | {r['length']:.1f} | {r['food']:.2f} | {r['thorns']:.2f} |"


def main():
    version = code_version()
    print(f"density check: {len(DENSITIES)} greedy settings + 1 random, {len(DEV_SEEDS)} episodes each", flush=True)
    results = {}
    for d in DENSITIES:
        print(f"sweep: greedy food_density={d}", flush=True)
        cfg = WorldConfig(food_density=d, thorn_density=THORN_DENSITY, respawn_delay=RESPAWN)
        results[d] = sweep(GreedyAgent, cfg, f"greedy_{d:.2f}", version)
    print("sweep: random at config default", flush=True)
    rand = sweep(RandomAgent, WorldConfig(), "random_default", version)

    print("\n| setting | faint rate | mean length | food/ep | thorns/ep |")
    print("|---|---|---|---|---|")
    for d, r in results.items():
        print(line(f"greedy {d:.2f}", r))
    dflt = WorldConfig()
    print(line(f"random {dflt.food_density:.2f} (default)", rand))
    print(f"invalid turns: greedy {sum(r['invalid'] for r in results.values())}, random {rand['invalid']}")
    ok = [d for d, r in results.items() if r["faint"] < TARGET_FAINT]
    print(f"lowest density with greedy faint rate < {TARGET_FAINT:.0%}: {min(ok) if ok else 'none'}")


if __name__ == "__main__":
    main()
