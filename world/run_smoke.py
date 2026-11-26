"""Smoke run: RandomAgent on the development seeds, both conditions.

Seeds 990000-990019 are reserved for development and are never used in a
pilot or confirmatory run. Each no-stakes twin ends on the turn its stakes
twin ended.

    python -m world.run_smoke
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world.agents import RandomAgent
from world.episode import run_episode
from world.log import code_version

DEV_SEEDS = range(990000, 990020)
OUT = Path(__file__).resolve().parent / "_smoke_logs"


def main(seeds=DEV_SEEDS, out=OUT):
    version = code_version()
    rows = []
    t0 = time.perf_counter()
    for seed in seeds:
        s = run_episode(RandomAgent(seed), condition="stakes", seed=seed, log_path=out / f"{seed}_stakes.jsonl.gz",
                        arm="smoke", version=version)
        n = run_episode(RandomAgent(seed), condition="no_stakes", seed=seed, max_turns=s["turns"],
                        log_path=out / f"{seed}_no_stakes.jsonl.gz", arm="smoke", version=version)
        assert n["turns"] == s["turns"]
        rows.append((seed, s, n))
    elapsed = time.perf_counter() - t0
    k = len(rows)

    def mean(xs):
        return sum(xs) / len(xs)

    sizes = [p.stat().st_size for p in out.glob("*.jsonl.gz")]
    print(f"episodes: {2 * k} ({k} seeds x 2 conditions)")
    print(f"stakes faint rate: {mean([s['fainted'] for _, s, _ in rows]):.2f}")
    print(f"mean episode length: {mean([s['turns'] for _, s, _ in rows]):.1f} turns")
    for name, i in (("stakes", 1), ("no_stakes", 2)):
        print(f"{name}: mean food eaten {mean([r[i]['food_eaten'] for r in rows]):.2f}, "
              f"mean thorns hit {mean([r[i]['thorns_hit'] for r in rows]):.2f}")
    print(f"seconds per episode: {elapsed / (2 * k):.4f}")
    print(f"log file size: mean {mean(sizes) / 1024:.1f} KB, max {max(sizes) / 1024:.1f} KB")
    for seed, s, _ in rows:
        print(f"  {seed}: {s['turns']} turns, fainted={s['fainted']}, food={s['food_eaten']}, thorns={s['thorns_hit']}")


if __name__ == "__main__":
    main()
