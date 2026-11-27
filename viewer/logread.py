"""Read episode logs for the viewer, including ones still being written.

An episode log is gzipped JSON Lines (world/log.py). The writer sync-flushes
after every line, so the bytes on disk always decode up to the last finished
line. read_partial() decodes whatever is there and drops a trailing half-line,
so it works on a running episode as well as a finished one.

Maps. Logs store only the starting map, so the map for each turn is rebuilt by
replaying the logged moves through CritterWorld with the episode's seed. Food
respawns come from a stream that depends only on the seed and on which cells
are free, so the replay matches the run. The replayed position is checked
against the logged one every turn. If they ever disagree, map_ok is False and
the viewer shows the starting map only, labeled as such.

Blinding (PREREGISTRATION.md, "Episode logs, replay viewer and dashboard").
During confirmatory runs the viewer shows coded labels and no check-in
results. A log is treated as blinded if its label isn't a plain condition name
or its header's phase is one of the config's blinded_phases. For those logs
this module strips, before anything leaves the server:
  - check-in answers and yes/no (the result itself),
  - meters (energy and health exist only with stakes, points only without),
    faints, and final meters, because any of them names the condition and
    would turn the coded label back into a plain one,
  - diary text, raw replies and edit text, because the critter writes its
    check-in answer into the diary and tends to talk about its body,
  - per-turn token counts and cost, because the two system prompts differ in
    length, so cost tracks the condition.
What stays is the map, where the critter walked, what it ate or stepped on,
which region it chose and which the game showed, and when tampers and
check-ins happened. Tamper timing comes from the seed and is the same for
both twins, so it carries no condition information.
Unblinding is a server flag (show_blinded), meant for after the primary test.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

PLAIN_CONDITIONS = ("stakes", "no_stakes")

BLIND_TURN_KEEP = (
    "type", "turn", "position", "move", "look_next", "chosen_region", "shown_region",
    "tamper_type", "checkin", "checkin_window", "ate", "thorn", "reply_valid",
)
BLIND_END_KEEP = ("type", "status", "turns", "food_eaten", "thorns_hit", "invalid_turns", "schedule")
HEADER_SHOW = ("arm", "model", "condition_code", "world_seed", "code_version", "phase", "tier", "effort")


def read_partial(path: str | Path) -> tuple[dict | None, list[dict], dict | None]:
    """Header, turn records and end record (None while running) from a log that may be mid-write."""
    data = Path(path).read_bytes()
    text = b""
    if data:
        d = zlib.decompressobj(wbits=31)  # gzip wrapper
        try:
            text = d.decompress(data)
        except zlib.error:
            text = b""
    lines = text.split(b"\n")
    if lines and lines[-1] != b"":
        lines = lines[:-1]  # half-written last line
    header, turns, end = None, [], None
    for raw in lines:
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            break
        kind = obj.get("type")
        if kind == "header":
            header = obj
        elif kind == "turn":
            turns.append(obj)
        elif kind == "end":
            end = obj
    return header, turns, end


def is_blinded(header: dict | None, blinded_phases=("confirmatory",)) -> bool:
    if not header:
        return False
    return header.get("condition_code") not in PLAIN_CONDITIONS or header.get("phase") in set(blinded_phases)


def replay_maps(header: dict, turns: list[dict]) -> tuple[list[list[str]], bool]:
    """Map rows at the start of each turn, and whether the replay matched the log."""
    start = list(header.get("start_map") or [])
    try:
        from world.env import CritterWorld
    except Exception:
        return [start for _ in turns], False
    env = CritterWorld("no_stakes")  # meters don't touch the map, and no_stakes never faints early
    try:
        env.reset(seed=int(header["world_seed"]))
    except Exception:
        return [start for _ in turns], False
    if env.map_rows() != start:
        return [start for _ in turns], False
    maps = []
    for rec in turns:
        if env.done or list(env.pos) != list(rec.get("position", [])):
            return [start for _ in turns], False
        maps.append(env.map_rows())
        try:
            look = rec.get("look_next")
            look = rec.get("chosen_region", 4) if look is None else look
            env.step({"move": rec["move"], "look": int(look), "diary": ""})
        except Exception:
            return [start for _ in turns], False
    return maps, True


def _reply_fields(rec: dict) -> dict:
    """The diary line and answer the critter wrote this turn, from its last raw reply."""
    raws = rec.get("raw_reply") or []
    if isinstance(raws, str):
        raws = [raws]
    for raw in reversed(raws):
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(obj, dict):
            return {"wrote": obj.get("diary"), "answer_field": obj.get("answer")}
    return {"wrote": None, "answer_field": None}


def _diary_edits(turns: list[dict]) -> list[dict]:
    edits = []
    for rec in turns:
        t = rec.get("tamper") or {}
        if t.get("type") == "diary_edit":
            edits.append({"at_turn": rec["turn"], "entry_turn": t.get("entry_turn"), "kind": t.get("edit_kind"),
                          "before": t.get("before"), "after": t.get("after")})
    return edits


def episode_view(path: str | Path, rel: str, *, blinded_phases=("confirmatory",), show_blinded: bool = False) -> dict:
    """Everything the browser needs for one episode, stripped if the log is blinded."""
    header, turns, end = read_partial(path)
    if header is None:
        return {"path": rel, "ready": False}
    maps, map_ok = replay_maps(header, turns)
    blind = is_blinded(header, blinded_phases) and not show_blinded
    out_turns = []
    for rec, m in zip(turns, maps):
        if blind:
            r = {k: rec.get(k) for k in BLIND_TURN_KEEP}
        else:
            r = {k: v for k, v in rec.items() if k != "calls"}  # raw API call records: big, not needed here
            r.update(_reply_fields(rec))
        r["map"] = m
        out_turns.append(r)
    if blind and end is not None:
        end = {k: end.get(k) for k in BLIND_END_KEEP}
    elif end is not None:
        end = {k: v for k, v in end.items() if k != "aborted_calls"}
    return {
        "path": rel,
        "ready": True,
        "blinded": blind,
        "header": {k: header.get(k) for k in HEADER_SHOW},
        "start_map": header.get("start_map"),
        "turns": out_turns,
        "end": end,
        "running": end is None,
        "map_ok": map_ok,
        "diary_edits": [] if blind else _diary_edits(turns),
    }


def episode_summary(path: Path, rel: str, *, blinded_phases=("confirmatory",), show_blinded: bool = False) -> dict:
    header, turns, end = read_partial(path)
    st = path.stat()
    return {
        "path": rel,
        "model": header.get("model") if header else None,
        "label": header.get("condition_code") if header else None,
        "phase": header.get("phase") if header else None,
        "tier": header.get("tier") if header else None,
        "seed": header.get("world_seed") if header else None,
        "blinded": is_blinded(header, blinded_phases) and not show_blinded,
        "turns": len(turns),
        "running": header is not None and end is None,
        "status": (end or {}).get("status", "done" if end else None),
        "mtime": st.st_mtime,
    }


def phase_spend(runs_dir: Path, caps: dict) -> list[dict]:
    """Total spend per phase from the runner's ledger, against its cap. Totals only: a per-episode
    or per-label split would leak the condition in blinded phases."""
    out = []
    ledger_dir = Path(runs_dir) / "ledger"
    if not ledger_dir.is_dir():
        return out
    for f in sorted(ledger_dir.glob("*.jsonl")):
        total = 0.0
        try:
            data = f.read_bytes()
        except OSError:
            continue
        for raw in data[: data.rfind(b"\n") + 1].split(b"\n"):
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if obj.get("type") == "response":
                total += float(obj.get("cost_usd") or 0)
        out.append({"phase": f.stem, "spend": round(total, 4), "cap": caps.get(f.stem)})
    return out
