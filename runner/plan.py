"""Seed lists and the shuffled pair order. No I/O beyond reading seed files."""

from __future__ import annotations

import random
from pathlib import Path

from runner.config import ALL_TIERS, DEV_SEEDS, PHASES, REAL_PHASES


class RunnerError(RuntimeError):
    """A problem that stops the runner before or between episodes (not an episode exclusion)."""


def read_seed_list(path: str | Path) -> list[int]:
    """One integer seed per line; blank lines and # comments are skipped. A missing file, a bad line
    or a repeated seed is an error."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise RunnerError(f"seed list file is missing: {path}. Seed lists are fixed by hand before a run; "
                          f"the runner does not make them.") from None
    seeds: list[int] = []
    for n, line in enumerate(lines, 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            seeds.append(int(line))
        except ValueError:
            raise RunnerError(f"{path} line {n}: not an integer seed: {line!r}") from None
    dupes = sorted({s for s in seeds if seeds.count(s) > 1})
    if dupes:
        raise RunnerError(f"{path}: repeated seeds {dupes[:5]}")
    if not seeds:
        raise RunnerError(f"{path}: no seeds in the file")
    return seeds


def check_phase_seeds(phase: str, seeds: list[int]) -> None:
    """Dev seeds (990000 to 990199) are for dev runs only; real phases never touch them, and a dev run
    never uses a seed that belongs to a real phase."""
    if phase not in PHASES:
        raise RunnerError(f"unknown phase {phase!r}")
    in_dev = [s for s in seeds if s in DEV_SEEDS]
    if phase in REAL_PHASES and in_dev:
        raise RunnerError(f"the {phase} phase refuses dev seeds ({DEV_SEEDS.start} to {DEV_SEEDS.stop - 1}); "
                          f"found {in_dev[:5]}")
    if phase == "dev" and len(in_dev) != len(seeds):
        raise RunnerError(f"dev runs may only use dev seeds ({DEV_SEEDS.start} to {DEV_SEEDS.stop - 1}), so no real "
                          f"seed is used up")


def check_disjoint(phase: str, seeds: list[int], others: dict[str, list[int]]) -> None:
    """The preregistration never reuses pilot seeds; the same holds for every pair of real phases."""
    if phase not in REAL_PHASES:
        return
    for other, other_seeds in others.items():
        if other != phase and other in REAL_PHASES:
            both = sorted(set(seeds) & set(other_seeds))
            if both:
                raise RunnerError(f"seeds {both[:5]} are in both the {phase} and {other} lists; phases never share seeds")


def build_slots(counts: dict[str, int], shuffle_seed: int, order: str = "shuffled") -> list[tuple[str, int]]:
    """Slots (tier, k) for every planned pair. Slot (tier, k) takes the tier's k-th usable seed, so every tier plays
    the same worlds. Always order the full plan, so running a subset keeps the same relative order.

    "shuffled": an order fixed by the shuffle seed, mixed across tiers.
    "alternate": k by k, each tier in turn (fable, mythos, fable, mythos, ...). No randomness: a stop at the cap
    leaves the tiers within one pair of each other, and nothing about the order depends on a seed."""
    if order == "alternate":
        most = max((counts.get(t, 0) for t in ALL_TIERS), default=0)
        return [(tier, k) for k in range(most) for tier in ALL_TIERS if k < counts.get(tier, 0)]
    if order != "shuffled":
        raise RunnerError(f"unknown pair order {order!r}")
    slots = [(tier, k) for tier in ALL_TIERS for k in range(counts.get(tier, 0))]
    random.Random(shuffle_seed).shuffle(slots)
    return slots
