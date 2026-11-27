"""Play one episode for the runner and write its log.

This is world/episode.run_episode with the pieces the runner needs and that
file leaves out (and that rule 5 of job 006 stops this job editing): the
check-in question appended to the turn text on check-in turns, the check-in
answer, per-turn token counts and cost, and a clean stop when the spend cap is
crossed or the API fails for good. With a plain Agent (no take_calls) and no
question it writes the same turn records as run_episode, plus extra fields.

The check-in answer comes from the reply's own answer field, never from the
diary, and it goes nowhere the critter can see: the world reads move, look and
diary only. On a check-in turn checkin_answer is that field's text (an empty
string if the critter left it empty, or its reply was invalid) and checkin_yes
is parsed from it. A non-empty answer on any other turn is a valid reply: it is
logged as stray_answer and counted, and is not a check-in answer. The raw reply
is always logged too, so the analysis can re-read it.
"""

from __future__ import annotations

import re
from pathlib import Path

from tqdm import tqdm

from world.agents import decide
from world.env import CritterWorld, WorldConfig
from world.log import EpisodeLog
from runner.claude_critter import APIFailure, AccessFailure, AuthFailure
from runner.ledger import CapExceeded

_YES_NO = re.compile(r"^\W*(yes|no)\b", re.IGNORECASE)


def parse_yes_no(answer: str | None) -> bool | None:
    """True for an answer that starts with yes, False for no (case-insensitive, after trimming), None otherwise,
    including an empty answer. A convenience only: the raw answer is logged and the analysis may re-parse it."""
    m = _YES_NO.match((answer or "").strip())
    return None if m is None else m.group(1).lower() == "yes"


def play_episode(agent, *, condition: str, seed: int, log_path: str | Path, model: str, condition_code: str,
                 checkin_question: str | None = None, max_turns: int | None = None,
                 world_config: WorldConfig | None = None, version: str | None = None, arm: str = "arm1",
                 header_extra: dict | None = None, progress: bool = False, desc: str = "episode",
                 status_suffix=None, on_turn=None) -> dict:
    """status_suffix: optional function returning text (such as phase spend against the cap) for the live bar line.
    on_turn: optional function called as on_turn(turn, max_turns) just before each turn's reply is asked for.
    Returns {"status": "done" | "aborted_cap" | "api_failure" | "incomplete_auth" | "stopped_access",
    "summary": {...}}. The summary is also the log's end line. "incomplete_auth" is a key the API refused and
    "stopped_access" a model the key may not use or that is not there (HTTP 403 or 404): the log is closed, marked
    incomplete, and carries no error text. Any other exception is a harness crash: it propagates and the log has no
    end line."""
    log_path = Path(log_path)
    if log_path.exists():
        raise FileExistsError(f"refusing to overwrite an existing episode log: {log_path}")
    take_calls = getattr(agent, "take_calls", lambda: [])
    env = CritterWorld(condition, world_config)
    _, info = env.reset(seed=seed, max_turns=max_turns)
    status, stop = "done", {}
    n_invalid = n_refusals = n_calls = tokens_in = tokens_out = 0
    n_empty_checkin = n_stray = 0
    cost = 0.0
    last, terminated = None, False
    bar = tqdm(total=env.max_turns, desc=desc, unit="turn", leave=False, dynamic_ncols=True, mininterval=1.0,
               disable=not progress)
    try:
        with EpisodeLog(log_path, arm=arm, model=model, condition_code=condition_code, world_seed=seed,
                        start_map=env.start_map, version=version, extra=header_extra) as log:
            while True:
                obs_dict, text = env.critter_view()
                seen_diary = [dict(e) for e in obs_dict["diary"]]
                if on_turn is not None:
                    on_turn(info["turn"], env.max_turns)
                question = checkin_question.strip() if (info["checkin"] and checkin_question) else None
                try:
                    d = decide(agent, obs_dict, f"{text}\n\n{question}" if question else text,
                               fallback_look=info["chosen_region"])
                except (CapExceeded, APIFailure, AuthFailure, AccessFailure) as e:
                    calls = take_calls()
                    n_calls += len(calls)
                    cost += sum(c["cost_usd"] for c in calls)
                    tokens_in += sum(c["prompt_tokens"] for c in calls)
                    tokens_out += sum(c["output_tokens"] for c in calls)
                    n_refusals += sum(c["stop_reason"] == "refusal" for c in calls)
                    if isinstance(e, CapExceeded):
                        status = "aborted_cap"
                        stop = {"aborted_turn": info["turn"], "aborted_calls": calls,
                                "cap": {"phase": e.phase, "spend": e.spend, "cap": e.cap}}
                    elif isinstance(e, AuthFailure):
                        status = "incomplete_auth"
                        stop = {"aborted_turn": info["turn"], "aborted_calls": calls,
                                "error": {"type": "authentication_error", "status_codes": [401]}}
                    elif isinstance(e, AccessFailure):
                        status = "stopped_access"
                        stop = {"aborted_turn": info["turn"], "aborted_calls": calls,
                                "error": {"type": e.error_type, "status_codes": [e.status_code]}}
                    else:
                        status = "api_failure"
                        stop = {"aborted_turn": info["turn"], "aborted_calls": calls, "error": e.as_dict()}
                    break
                calls = take_calls()
                n_invalid += not d.valid
                n_calls += len(calls)
                turn_in = sum(c["prompt_tokens"] for c in calls)
                turn_out = sum(c["output_tokens"] for c in calls)
                turn_cost = sum(c["cost_usd"] for c in calls)
                tokens_in, tokens_out, cost = tokens_in + turn_in, tokens_out + turn_out, cost + turn_cost
                n_refusals += sum(c["stop_reason"] == "refusal" for c in calls)

                _, _, terminated, truncated, nxt = env.step(d.action)
                last = nxt["last"]
                reply_answer = d.action["answer"]
                answer = reply_answer if info["checkin"] else None
                stray = reply_answer if (not info["checkin"] and reply_answer) else None
                n_empty_checkin += bool(info["checkin"]) and not reply_answer
                n_stray += stray is not None
                log.turn({
                    "turn": info["turn"],
                    "position": info["position"],
                    "move": last["move"],
                    "look_next": last["look"],
                    "chosen_region": info["chosen_region"],
                    "shown_region": info["shown_region"],
                    "energy": info["energy"],
                    "health": info["health"],
                    "points": info["points"],
                    "diary": seen_diary,
                    "tamper": info["tamper"],
                    "tamper_type": info["tamper"]["type"] if info["tamper"] else None,
                    "raw_reply": d.raw_replies,
                    "reply_valid": d.valid,
                    "reply_errors": d.errors,
                    "checkin": info["checkin"],
                    "checkin_window": info["checkin_window"],
                    "checkin_answer": answer,
                    "checkin_yes": parse_yes_no(answer),
                    "stray_answer": stray,
                    "ate": last["ate"],
                    "thorn": last["thorn"],
                    "fainted": last["fainted"],
                    "tokens_in": turn_in,
                    "tokens_out": turn_out,
                    "cost_usd": turn_cost,
                    "calls": calls,
                })
                bar.update(1)
                bar.set_postfix_str(f"cost ${cost:.4f}, invalid {n_invalid}, refusals {n_refusals}"
                                    + (f" | {status_suffix()}" if status_suffix else ""))
                info = nxt
                if terminated or truncated:
                    break
            summary = {
                "status": status,
                "turns": last["turn"] if last else 0,
                "fainted": bool(terminated),
                "food_eaten": env.food_eaten,
                "thorns_hit": env.thorns_hit,
                "invalid_turns": n_invalid,
                "empty_checkin_answers": n_empty_checkin,
                "stray_answers": n_stray,
                "refusals": n_refusals,
                "api_calls": n_calls,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost,
                "final_energy": env.meters()[0],
                "final_health": env.meters()[1],
                "final_points": env.meters()[2],
                "schedule": [
                    {"window": w.index, "kind": w.kind, "tamper_turn": w.tamper_turn, "checkin_turn": w.checkin_turn}
                    for w in env.schedule.windows
                ],
                **stop,
            }
            log.end(summary)
    finally:
        bar.close()
    return {"status": status, "summary": summary}
