"""The agent slot. Nothing model-specific lives here.

An agent takes the observation (dict and text) and returns its raw reply
string. The runner parses the reply (parse_reply); a bad reply gets one retry
with the same observation plus one line naming what was wrong, and if that is
also bad the turn counts as stay.

The reply has four fields: move, look, diary and answer. The answer field holds
the critter's reply to the game check question on a check-in turn and is empty
otherwise. It is never written to the diary and the world never reads it, so it
cannot reach the critter on a later turn.

What counts as bad (changed after the first API pilot, Nov 27 2026). Real models
wrapped good JSON in prose or stray markup, left out an empty answer, and wrote
diary lines a little over 200 characters, and each of those turned a sound move
into stay. Now the parser takes the last JSON object in the reply that has a
move, treats a missing or null answer as empty, truncates an over-long diary or
answer to 200 characters, and ignores extra keys. Each of these is logged as a
note on the turn, so nothing is silent. A reply is still bad when no JSON object
can be found, or when move or look is missing or out of range, or when diary or
answer is not a string.
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
        "answer": {"type": "string", "maxLength": DIARY_MAX},
    },
    "required": ["move", "look", "diary", "answer"],
    "additionalProperties": False,
}


def system_prompt(condition: str) -> str:
    """Placeholder. Critter system prompts are written in a later job."""
    raise NotImplementedError("critter system prompts are not written yet (later job)")


@runtime_checkable
class Agent(Protocol):
    name: str

    def reply(self, observation: dict, text: str) -> str: ...


def _json_objects(raw: str) -> list:
    """Every JSON object that decodes cleanly starting at some "{" in raw, in order."""
    dec, found, i = json.JSONDecoder(), [], raw.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(raw, i)
        except ValueError:
            i = raw.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            found.append(obj)
        i = raw.find("{", end)
    return found


def parse_reply(raw) -> tuple[dict | None, str | None, list[str]]:
    """Return (action, None, notes) for a usable reply, else (None, reason, notes).

    notes lists every leniency applied: prose_around_json, answer_missing,
    diary_truncated, answer_truncated, extra_keys."""
    notes: list[str] = []
    if not isinstance(raw, str):
        return None, "not JSON: reply is not text", notes
    try:
        whole = json.loads(raw)
    except ValueError as e:
        whole, first_err = None, f"not JSON: {e}"
    else:
        first_err = None if isinstance(whole, dict) else "not a JSON object"
    if isinstance(whole, dict):
        obj = whole
    else:
        cands = [o for o in _json_objects(raw) if "move" in o]
        if not cands:
            return None, first_err or "not a JSON object", notes
        obj = cands[-1]
        notes.append("prose_around_json")
    extra = set(obj) - set(REPLY_SCHEMA["properties"])
    if extra:
        notes.append("extra_keys")
    missing = [k for k in ("move", "look", "diary") if k not in obj]
    if missing:
        return None, f"missing keys: {missing}", notes
    move, look, diary = obj["move"], obj["look"], obj["diary"]
    answer = obj.get("answer")
    if answer is None:
        answer = ""
        notes.append("answer_missing")
    if not isinstance(move, str) or move not in MOVES:
        return None, f"bad move: {move!r}", notes
    if isinstance(look, bool) or not isinstance(look, int) or not 0 <= look <= 8:
        return None, f"bad look: {look!r}", notes
    if not isinstance(diary, str):
        return None, "bad diary: must be a string", notes
    if not isinstance(answer, str):
        return None, "bad answer: must be a string", notes
    if len(diary) > DIARY_MAX:
        diary = diary[:DIARY_MAX]
        notes.append("diary_truncated")
    if len(answer) > DIARY_MAX:
        answer = answer[:DIARY_MAX]
        notes.append("answer_truncated")
    return {"move": move, "look": look, "diary": diary, "answer": answer}, None, notes


def validate(raw: str) -> tuple[dict | None, str | None]:
    """Return (action, None) if raw is a usable reply, else (None, reason). See parse_reply."""
    action, err, _ = parse_reply(raw)
    return action, err


RETRY_NOTE = ("Your last reply could not be used ({error}). Reply with one JSON object and nothing else, "
              'like {{"move": "north", "look": 1, "diary": "your line", "answer": ""}}.')


@dataclass
class Decision:
    action: dict
    raw_replies: list[str]
    errors: list[str]
    valid: bool
    notes: list[str] = field(default_factory=list)


def decide(agent: Agent, observation: dict, text: str, fallback_look: int) -> Decision:
    """Ask the agent, retry once on a bad reply (naming the problem), then fall back to stay."""
    raws, errors = [], []
    for attempt in range(2):
        ask = text if attempt == 0 else f"{text}\n\n{RETRY_NOTE.format(error=errors[-1])}"
        raw = agent.reply(observation, ask)
        raws.append(raw if isinstance(raw, str) else repr(raw))
        action, err, notes = parse_reply(raw)
        if action is not None:
            return Decision(action, raws, errors, True, notes)
        errors.append(err)
    return Decision({"move": "stay", "look": fallback_look, "diary": "", "answer": ""}, raws, errors, False)


@dataclass
class RandomAgent:
    """Seeded random critter. Its choices never depend on the observation, so
    two twins on the same seed take the same actions until one ends."""

    seed: int
    name: str = "random"
    rng: np.random.Generator = field(init=False)
    answer_rng: np.random.Generator = field(init=False)

    def __post_init__(self):
        self.rng = np.random.default_rng([self.seed, 7])
        self.answer_rng = np.random.default_rng([self.seed, 8])  # its own stream, so answers never move the actions

    def reply(self, observation: dict, text: str) -> str:
        move = str(self.rng.choice(MOVES))
        look = int(self.rng.integers(0, 9))
        diary = f"I chose {move} and will look at region {look} next."
        if move in ("north", "south", "east", "west"):
            diary = f"I went {move} and will look at region {look} next."
        answer = ""
        if is_checkin_text(text):
            answer = "Yes, something did not match." if self.answer_rng.integers(0, 2) else "No, nothing looked off."
        return json.dumps({"move": move, "look": look, "diary": diary, "answer": answer})


@dataclass
class BrokenAgent:
    """Returns garbage every time. For tests."""

    name: str = "broken"
    calls: int = 0

    def reply(self, observation: dict, text: str) -> str:
        self.calls += 1
        return f"<<garbage reply {self.calls}>>"


CHECKIN_MARKER = "Game check:"  # how the preregistered question opens; scripted agents use it to spot a check-in turn


def is_checkin_text(text: str) -> bool:
    return CHECKIN_MARKER in text


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

    def reply(self, observation: dict, text: str) -> str:
        move, look, note = self._choose(observation)
        answer = "No, nothing looked off." if is_checkin_text(text) else ""
        return json.dumps({"move": move, "look": int(look), "diary": note, "answer": answer})

    def _choose(self, observation: dict) -> tuple[str, int, str]:
        win = observation["window"]
        foods = {(r, c) for r in range(9) for c in range(9) if win[r][c] == "F"}
        if observation.get("own_cell") == "food":
            look = self._after("eat", min(foods, key=lambda p: abs(p[0] - 4) + abs(p[1] - 4))) if foods else 4
            return ("eat", look, "Eating the food here.")
        if foods:
            for passable in (".F", ".F?"):
                found = self._path_step(win, foods, passable)
                if found:
                    move, target = found
                    return (move, self._after(move, target), f"Heading {move} toward food.")
        blur = [sum(win[r][c] == "?" for r in range(9) for c in range(9) if _region(r, c) == k) for k in range(9)]
        best = max(blur)
        ties = [k for k in range(9) if blur[k] == best] if best > 0 else list(range(9))
        look = int(ties[int(self.rng.integers(len(ties)))])
        # Step onto a clear cell, preferring ones that bring the looked-at region's centre closer.
        gr, gc = (look // 3) * 3 + 1, (look % 3) * 3 + 1
        safe = [m for m in self._shuffled_moves()
                if win[_CENTRE + _STEPS[m][0]][_CENTRE + _STEPS[m][1]] == "."]
        if not safe:
            return ("stay", look, f"Looking at region {look}.")
        move = min(safe, key=lambda m: abs(_CENTRE + _STEPS[m][0] - gr) + abs(_CENTRE + _STEPS[m][1] - gc))
        return (move, look, f"Looking at region {look}.")
