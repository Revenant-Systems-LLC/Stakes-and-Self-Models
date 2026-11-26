"""Run one episode with one agent and write its log.

Check-in questions are not generated here. On a check-in turn the record says
checkin=true and checkin_answer stays null until a later job supplies the
question (see checkin_question below).
"""

from __future__ import annotations

from pathlib import Path

from world import blinding
from world.agents import Agent, decide
from world.env import CritterWorld, WorldConfig
from world.log import EpisodeLog


def checkin_question() -> str:
    """Placeholder. The check-in question text comes in a later job."""
    raise NotImplementedError("check-in question text is not written yet (later job)")


def run_episode(agent: Agent, *, condition: str, seed: int, log_path: str | Path, arm: str = "dev",
                model: str | None = None, condition_code: str | None = None, max_turns: int | None = None,
                config: WorldConfig | None = None, version: str | None = None, blinded: bool = False,
                key_path: str | None = None) -> dict:
    """blinded=True takes the header's condition code from the blinding key
    (confirmatory runs); blinded=False writes the plain name (pilots)."""
    if blinded and condition_code is not None:
        raise ValueError("a blinded run takes its condition code from the key, not from the caller")
    if condition_code is None:
        condition_code = blinding.condition_code(condition, blinded=blinded, path=key_path)
    env = CritterWorld(condition, config)
    _, info = env.reset(seed=seed, max_turns=max_turns)
    with EpisodeLog(log_path, arm=arm, model=model or agent.name, condition_code=condition_code,
                    world_seed=seed, start_map=env.start_map, version=version) as log:
        n_invalid = 0
        while True:
            obs_dict, text = env.critter_view()
            seen_diary = [dict(e) for e in obs_dict["diary"]]
            d = decide(agent, obs_dict, text, fallback_look=info["chosen_region"])
            n_invalid += not d.valid
            _, _, terminated, truncated, nxt = env.step(d.action)
            last = nxt["last"]
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
                "checkin_answer": None,
                "ate": last["ate"],
                "thorn": last["thorn"],
                "fainted": last["fainted"],
                "tokens_in": None,
                "tokens_out": None,
                "cost_usd": None,
            })
            info = nxt
            if terminated or truncated:
                break
        summary = {
            "turns": last["turn"],
            "fainted": bool(terminated),
            "food_eaten": env.food_eaten,
            "thorns_hit": env.thorns_hit,
            "invalid_turns": n_invalid,
            "final_energy": env.meters()[0],
            "final_health": env.meters()[1],
            "final_points": env.meters()[2],
            "schedule": [
                {"window": w.index, "kind": w.kind, "tamper_turn": w.tamper_turn, "checkin_turn": w.checkin_turn}
                for w in env.schedule.windows
            ],
        }
        log.end(summary)
    return summary
