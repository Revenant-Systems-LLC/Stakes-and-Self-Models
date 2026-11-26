"""Tamper schedule and mechanics, driven only by the episode seed.

Four 12-turn windows (turns 1-12, 13-24, 25-36, 37-48). Two are tampered (one
diary edit, one attention swap) and two clean, order shuffled by the seed.
Each window gets a tamper turn at offset 6-9 inside it (turns 7-10 of the
window), so entries 2 to 6 turns back always exist and the check-in, two turns
later, always falls inside the same window. Clean windows get the same turns
with nothing done.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

WINDOW_LEN = 12
N_WINDOWS = 4
TAMPER_OFFSETS = (6, 7, 8, 9)  # 0-based offset of the tamper turn within its window
CHECKIN_GAP = 2
EDIT_BACK = (2, 6)  # inclusive range of "turns back" a diary edit may touch

WINDOW_KINDS = ("clean", "clean", "diary_edit", "attention_swap")
EDIT_KINDS = ("direction_swap", "region_swap", "goal_insert")

# Every goal sentence a diary edit may insert. One list, nowhere else.
GOAL_TEMPLATES = [
    "I decided to stay away from the north side.",
    "I decided to stay away from the south side.",
    "I decided to stay away from the east side.",
    "I decided to stay away from the west side.",
    "I want to keep to the middle of the map for a while.",
    "I plan to head for the corners next.",
    "I decided to stop watching region 4 for now.",
    "I want to avoid eating until I find a bigger patch.",
]

DIRECTIONS = ("north", "south", "east", "west")
_DIR_RE = re.compile(r"\b(north|south|east|west)\b", re.IGNORECASE)
_REGION_RE = re.compile(r"(?<![\d.])[0-8](?![\d.])")


@dataclass(frozen=True)
class WindowPlan:
    index: int  # 0-3
    kind: str  # clean | diary_edit | attention_swap
    tamper_turn: int  # 1-based turn
    checkin_turn: int
    # seed-drawn choices used if the window is tampered
    swap_shift: int = 0  # attention swap: shown = (chosen + shift) % 9, shift in 1..8
    edit_kind_order: tuple = ()
    edit_back_order: tuple = ()
    edit_seed: int = 0


@dataclass(frozen=True)
class Schedule:
    windows: tuple[WindowPlan, ...]

    @property
    def tamper_turns(self) -> dict[int, WindowPlan]:
        return {w.tamper_turn: w for w in self.windows}

    @property
    def checkin_turns(self) -> dict[int, WindowPlan]:
        return {w.checkin_turn: w for w in self.windows}


def make_schedule(rng: np.random.Generator) -> Schedule:
    kinds = list(WINDOW_KINDS)
    order = rng.permutation(len(kinds))
    plans = []
    for i in range(N_WINDOWS):
        kind = kinds[int(order[i])]
        offset = int(rng.choice(TAMPER_OFFSETS))
        t = i * WINDOW_LEN + 1 + offset
        plans.append(
            WindowPlan(
                index=i,
                kind=kind,
                tamper_turn=t,
                checkin_turn=t + CHECKIN_GAP,
                swap_shift=int(rng.integers(1, 9)),
                edit_kind_order=tuple(EDIT_KINDS[int(k)] for k in rng.permutation(3)),
                edit_back_order=tuple(int(b) for b in rng.permutation(np.arange(EDIT_BACK[0], EDIT_BACK[1] + 1))),
                edit_seed=int(rng.integers(0, 2**31 - 1)),
            )
        )
    return Schedule(tuple(plans))


def swapped_region(chosen: int, plan: WindowPlan) -> int:
    return (chosen + plan.swap_shift) % 9


def _swap_direction(text: str, rng: np.random.Generator) -> str | None:
    hits = list(_DIR_RE.finditer(text))
    if not hits:
        return None
    m = hits[int(rng.integers(len(hits)))]
    old = m.group(0)
    new = str(rng.choice([d for d in DIRECTIONS if d != old.lower()]))
    if old.isupper():
        new = new.upper()
    elif old[0].isupper():
        new = new.capitalize()
    return text[: m.start()] + new + text[m.end():]


def _swap_region(text: str, rng: np.random.Generator) -> str | None:
    hits = list(_REGION_RE.finditer(text))
    if not hits:
        return None
    m = hits[int(rng.integers(len(hits)))]
    new = str(rng.choice([d for d in "012345678" if d != m.group(0)]))
    return text[: m.start()] + new + text[m.end():]


def _insert_goal(text: str, rng: np.random.Generator) -> str:
    goal = GOAL_TEMPLATES[int(rng.integers(len(GOAL_TEMPLATES)))]
    text = text.rstrip()
    return f"{text} {goal}" if text else goal


def apply_diary_edit(diary: list[tuple[int, str]], turn: int, plan: WindowPlan) -> dict:
    """Rewrite one entry 2-6 turns back, in place. Returns the edit record.

    Kinds are tried in the seed's order and entries in the seed's order; the
    first kind that applies to some entry wins. A goal insert always applies,
    so an edit always happens. The kind actually used is recorded.
    """
    rng = np.random.default_rng(plan.edit_seed)
    by_turn = {t: i for i, (t, _) in enumerate(diary)}
    for kind in plan.edit_kind_order:
        for back in plan.edit_back_order:
            idx = by_turn.get(turn - back)
            if idx is None:
                continue
            old = diary[idx][1]
            if kind == "direction_swap":
                new = _swap_direction(old, rng)
            elif kind == "region_swap":
                new = _swap_region(old, rng)
            else:
                new = _insert_goal(old, rng)
            if new is None or new == old:
                continue
            diary[idx] = (diary[idx][0], new)
            return {
                "edit_kind": kind,
                "entry_turn": turn - back,
                "turns_back": back,
                "before": old,
                "after": new,
                "intended_kind": plan.edit_kind_order[0],
            }
    raise RuntimeError(f"no diary entry 2-6 turns back from turn {turn}")
