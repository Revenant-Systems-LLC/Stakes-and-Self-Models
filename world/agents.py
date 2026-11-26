"""The agent slot. Nothing model-specific lives here.

An agent takes the observation (dict and text) and returns its raw reply
string. The runner validates the reply against REPLY_SCHEMA; a bad reply gets
one retry with the same observation, and if that is also bad the turn counts
as stay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from world.env import DIARY_MAX, MOVES

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "move": {"type": "string", "enum": list(MOVES)},
        "look": {"type": "integer", "minimum": 0, "maximum": 8},
        "diary": {"type": "string", "maxLength": DIARY_MAX},
    },
    "required": ["move", "look", "diary"],
    "additionalProperties": False,
}


def system_prompt(condition: str) -> str:
    """Placeholder. Critter system prompts are written in a later job."""
    raise NotImplementedError("critter system prompts are not written yet (later job)")


@runtime_checkable
class Agent(Protocol):
    name: str

    def reply(self, observation: dict, text: str) -> str: ...


def validate(raw: str) -> tuple[dict | None, str | None]:
    """Return (action, None) if raw is a valid reply, else (None, reason)."""
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError) as e:
        return None, f"not JSON: {e}"
    if not isinstance(obj, dict):
        return None, "not a JSON object"
    extra = set(obj) - set(REPLY_SCHEMA["properties"])
    if extra:
        return None, f"unexpected keys: {sorted(extra)}"
    missing = [k for k in REPLY_SCHEMA["required"] if k not in obj]
    if missing:
        return None, f"missing keys: {missing}"
    move, look, diary = obj["move"], obj["look"], obj["diary"]
    if not isinstance(move, str) or move not in MOVES:
        return None, f"bad move: {move!r}"
    if isinstance(look, bool) or not isinstance(look, int) or not 0 <= look <= 8:
        return None, f"bad look: {look!r}"
    if not isinstance(diary, str) or len(diary) > DIARY_MAX:
        return None, "bad diary: must be a string of at most %d characters" % DIARY_MAX
    return {"move": move, "look": look, "diary": diary}, None


@dataclass
class Decision:
    action: dict
    raw_replies: list[str]
    errors: list[str]
    valid: bool


def decide(agent: Agent, observation: dict, text: str, fallback_look: int) -> Decision:
    """Ask the agent, retry once on a bad reply, then fall back to stay."""
    raws, errors = [], []
    for _ in range(2):
        raw = agent.reply(observation, text)
        raws.append(raw if isinstance(raw, str) else repr(raw))
        action, err = validate(raw)
        if action is not None:
            return Decision(action, raws, errors, True)
        errors.append(err)
    return Decision({"move": "stay", "look": fallback_look, "diary": ""}, raws, errors, False)


@dataclass
class RandomAgent:
    """Seeded random critter. Its choices never depend on the observation, so
    two twins on the same seed take the same actions until one ends."""

    seed: int
    name: str = "random"
    rng: np.random.Generator = field(init=False)

    def __post_init__(self):
        self.rng = np.random.default_rng([self.seed, 7])

    def reply(self, observation: dict, text: str) -> str:
        move = str(self.rng.choice(MOVES))
        look = int(self.rng.integers(0, 9))
        diary = f"I chose {move} and will look at region {look} next."
        if move in ("north", "south", "east", "west"):
            diary = f"I went {move} and will look at region {look} next."
        return json.dumps({"move": move, "look": look, "diary": diary})


@dataclass
class BrokenAgent:
    """Returns garbage every time. For tests."""

    name: str = "broken"
    calls: int = 0

    def reply(self, observation: dict, text: str) -> str:
        self.calls += 1
        return f"<<garbage reply {self.calls}>>"


# Window geometry for scripted agents (kept local so agents.py does not import observe).
_CENTRE = 4
_STEPS = {"north": (-1, 0), "south": (1, 0), "east": (0, 1), "west": (0, -1)}


def _region(r: int, c: int) -> int:
    return (r // 3) * 3 + (c // 3)


@dataclass
class GreedyAgent:
    """Scripted forager for tuning food density. Reads only the structured
    observation (window rows and own_cell).

    Eat when standing on food. Otherwise walk the shortest path toward the
    nearest food seen in full detail ("F"), never onto a seen thorn ("T") and
    onto blur ("?") only if no clear path exists, and keep looking at the
    region the target will be in. With no food in sight, look at the region
    with the most blur and step toward it. Ties are broken by a seeded RNG.
    """

    seed: int
    name: str = "greedy"
    rng: np.random.Generator = field(init=False)

    def __post_init__(self):
        self.rng = np.random.default_rng([self.seed, 11])

    def _shuffled_moves(self) -> list[str]:
        return [list(_STEPS)[i] for i in self.rng.permutation(len(_STEPS))]

    def _path_step(self, win: list[str], goal: set[tuple[int, int]], passable: str) -> tuple[str, tuple[int, int]] | None:
        """BFS from the centre; return (first move, goal reached) or None."""
        start = (_CENTRE, _CENTRE)
        first = {start: None}
        frontier = [start]
        while frontier:
            nxt = []
            for cell in frontier:
                if cell in goal:
                    return first[cell], cell
                for m in self._shuffled_moves():
                    dr, dc = _STEPS[m]
                    r, c = cell[0] + dr, cell[1] + dc
                    if not (0 <= r < 9 and 0 <= c < 9) or (r, c) in first:
                        continue
                    if win[r][c] not in passable and (r, c) not in goal:
                        continue
                    first[(r, c)] = first[cell] or m
                    nxt.append((r, c))
            frontier = nxt
        return None

    def _after(self, move: str, cell: tuple[int, int]) -> int:
        """Region of cell in next turn's window, after the critter moves."""
        dr, dc = _STEPS.get(move, (0, 0))
        r = min(8, max(0, cell[0] - dr))
        c = min(8, max(0, cell[1] - dc))
        return _region(r, c)

    def _reply(self, move: str, look: int, note: str) -> str:
        return json.dumps({"move": move, "look": int(look), "diary": note})

    def reply(self, observation: dict, text: str) -> str:
        win = observation["window"]
        foods = {(r, c) for r in range(9) for c in range(9) if win[r][c] == "F"}
        if observation.get("own_cell") == "food":
            look = self._after("eat", min(foods, key=lambda p: abs(p[0] - 4) + abs(p[1] - 4))) if foods else 4
            return self._reply("eat", look, "Eating the food here.")
        if foods:
            for passable in (".F", ".F?"):
                found = self._path_step(win, foods, passable)
                if found:
                    move, target = found
                    return self._reply(move, self._after(move, target), f"Heading {move} toward food.")
        blur = [sum(win[r][c] == "?" for r in range(9) for c in range(9) if _region(r, c) == k) for k in range(9)]
        best = max(blur)
        ties = [k for k in range(9) if blur[k] == best] if best > 0 else list(range(9))
        look = int(ties[int(self.rng.integers(len(ties)))])
        # Step onto a clear cell, preferring ones that bring the looked-at region's centre closer.
        gr, gc = (look // 3) * 3 + 1, (look % 3) * 3 + 1
        safe = [m for m in self._shuffled_moves()
                if win[_CENTRE + _STEPS[m][0]][_CENTRE + _STEPS[m][1]] == "."]
        if not safe:
            return self._reply("stay", look, f"Looking at region {look}.")
        move = min(safe, key=lambda m: abs(_CENTRE + _STEPS[m][0] - gr) + abs(_CENTRE + _STEPS[m][1] - gc))
        return self._reply(move, look, f"Looking at region {look}.")
