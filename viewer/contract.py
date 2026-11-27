"""The data contract between the study's runs and the viewer.

logread.episode_view() turns a log into the episode object the browser gets from
/api/episode. This module states what that object must look like and checks it,
so a change on the runner side (a renamed field, a new turn key, a map that
doesn't add up) shows up as a failing test instead of a viewer that quietly
draws the wrong thing.

The blinding part is the one that matters most: for a blinded episode, a turn may
carry only the keys in logread.BLIND_TURN_KEEP plus the replayed map, and the end
line only logread.BLIND_END_KEEP. Any other key fails the check, so a new runner
field can't leak the condition by default. It has to be added to the keep list on
purpose.

    from viewer import contract
    problems = contract.check_episode(view)   # [] means the episode meets the contract
"""

from __future__ import annotations

from viewer import logread

N = 11
TILES = set(".FT")
MOVES = ("north", "south", "east", "west", "stay", "eat")
STEP = {"north": (-1, 0), "south": (1, 0), "east": (0, 1), "west": (0, -1)}
TOP_KEYS = ("path", "ready", "blinded", "header", "start_map", "turns", "end", "running", "stopped", "map_ok",
            "diary_edits")
TURN_REQUIRED = ("turn", "position", "move", "chosen_region", "shown_region", "map")
TAMPER_TYPES = (None, "attention_swap", "diary_edit")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def check_map(rows, where: str) -> list[str]:
    if not isinstance(rows, list) or len(rows) != N:
        return [f"{where}: map must be {N} rows"]
    for i, row in enumerate(rows):
        if not isinstance(row, str) or len(row) != N or set(row) - TILES:
            return [f"{where}: map row {i} must be {N} characters of '.', 'F' or 'T'"]
    return []


def _check_pos(p, where: str) -> list[str]:
    if not (isinstance(p, list) and len(p) == 2 and all(_is_int(x) and 0 <= x < N for x in p)):
        return [f"{where}: position must be [row, col] inside the {N}x{N} pool"]
    return []


def check_turns(turns: list, blinded: bool) -> list[str]:
    problems: list[str] = []
    allowed = set(logread.BLIND_TURN_KEEP) | {"map"}
    prev = None
    for i, rec in enumerate(turns):
        where = f"turn #{i}"
        if not isinstance(rec, dict):
            problems.append(f"{where}: must be an object")
            continue
        missing = [k for k in TURN_REQUIRED if k not in rec]
        if missing:
            problems.append(f"{where}: missing {missing}")
            continue
        where = f"turn {rec['turn']}"
        if not _is_int(rec["turn"]) or rec["turn"] < 0:
            problems.append(f"{where}: turn must be a whole number")
        problems += _check_pos(rec["position"], where)
        problems += check_map(rec["map"], where)
        if rec["move"] not in MOVES:
            problems.append(f"{where}: move {rec['move']!r} isn't one of {list(MOVES)}")
        for k in ("chosen_region", "shown_region"):
            if not (_is_int(rec[k]) and 0 <= rec[k] <= 8):
                problems.append(f"{where}: {k} must be 0 to 8")
        if rec.get("tamper_type") not in TAMPER_TYPES:
            problems.append(f"{where}: unknown tamper_type {rec.get('tamper_type')!r}")
        if blinded:
            leaked = sorted(set(rec) - allowed)
            if leaked:
                problems.append(f"{where}: blinded turn carries {leaked}, which aren't on the blind keep list")
        if prev is not None and not any(p.startswith(f"turn {prev['turn']}") for p in problems):
            if _is_int(rec["turn"]) and _is_int(prev["turn"]) and rec["turn"] != prev["turn"] + 1:
                problems.append(f"{where}: follows turn {prev['turn']}, turns must count up by one")
            pr, pc = prev["position"]
            r, c = rec["position"]
            dr, dc = STEP.get(prev["move"], (0, 0))
            # a move into the edge of the pool leaves the critter where it was
            if (r, c) not in {(pr + dr, pc + dc), (pr, pc)}:
                problems.append(f"{where}: at {rec['position']} after moving {prev['move']} from {prev['position']}")
        prev = rec
    return problems


def check_episode(view) -> list[str]:
    """Every way an episode object breaks the contract, as plain sentences."""
    if not isinstance(view, dict):
        return ["the episode must be an object"]
    if view.get("ready") is False:
        return [] if set(view) <= {"path", "ready"} else ["a not-ready episode carries only path and ready"]
    problems = [f"missing top-level key {k!r}" for k in TOP_KEYS if k not in view]
    if problems:
        return problems
    blinded = view["blinded"]
    if not isinstance(blinded, bool):
        problems.append("blinded must be true or false")
    header = view["header"]
    if not isinstance(header, dict) or set(header) != set(logread.HEADER_SHOW):
        problems.append(f"header must carry exactly {list(logread.HEADER_SHOW)}")
    problems += check_map(view["start_map"], "start_map")
    turns = view["turns"]
    if not isinstance(turns, list):
        return problems + ["turns must be a list"]
    problems += check_turns(turns, bool(blinded))
    if turns and view["map_ok"] and turns[0].get("map") != view["start_map"]:
        problems.append("map_ok is true but turn 0's map isn't the start map")
    end = view["end"]
    if end is not None:
        if not isinstance(end, dict):
            problems.append("end must be an object or null")
        elif blinded and set(end) - set(logread.BLIND_END_KEEP):
            problems.append(f"blinded end line carries {sorted(set(end) - set(logread.BLIND_END_KEEP))}")
    if view["running"] and (end is not None or view["stopped"]):
        problems.append("a running episode has no end line and isn't stopped")
    if blinded and view["diary_edits"]:
        problems.append("a blinded episode must not carry diary edit text")
    return problems
