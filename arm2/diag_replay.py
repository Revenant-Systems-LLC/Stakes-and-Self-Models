"""Job 009 step 1: replay a logged episode through the world and list, per turn, what the critter was shown.

    python -m arm2.diag_replay [log.jsonl.gz] [--out M:\\Projects\\Lobster-Lab\\runs\\arm2\\diag]

CPU only, no model. The world is deterministic from its seed, so feeding the logged
moves back in rebuilds exactly what the critter saw. The replay is checked against
the log (position, energy, health, shown region every turn).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world import observe
from world.env import CritterWorld
from world.log import read_log

DEFAULT_LOG = Path(r"M:\Projects\Lobster-Lab\runs\arm2\episodes\990000_stakes.jsonl.gz")
DEFAULT_OUT = Path(r"M:\Projects\Lobster-Lab\runs\arm2\diag")


def count_in_region(win: list[str], region: int, ch: str) -> int:
    return sum(win[r][c] == ch for r in range(9) for c in range(9) if observe.region_of(r, c) == region)


def true_grid_counts(grid, pos, ch_code: int) -> dict:
    """Where the real food is in the 9x9 window, by region (ignores blur)."""
    out = {}
    for r in range(9):
        for c in range(9):
            wr, wc = pos[0] - 4 + r, pos[1] - 4 + c
            if 0 <= wr < grid.shape[0] and 0 <= wc < grid.shape[1] and int(grid[wr, wc]) == ch_code:
                k = observe.region_of(r, c)
                out[k] = out.get(k, 0) + 1
    return out


def replay(log_path: Path) -> list[dict]:
    header, turns, end = read_log(log_path)
    seed, cond = header["world_seed"], header["condition_code"]  # plain name in unblinded dev runs
    assert cond in ("stakes", "no_stakes"), cond
    env = CritterWorld(cond)
    env.reset(seed=seed, max_turns=None)
    rows = []
    for rec in turns:
        obs, _ = env.critter_view()
        win = obs["window"]
        assert env.turn == rec["turn"], (env.turn, rec["turn"])
        assert list(env.pos) == list(rec["position"]), (rec["turn"], env.pos, rec["position"])
        assert env.shown_region == rec["shown_region"], rec["turn"]
        reply = json.loads(rec["raw_reply"][0]) if rec["reply_valid"] else {}
        shown = rec["shown_region"]
        rows.append({
            "turn": rec["turn"], "pos": list(env.pos), "energy": rec["energy"], "health": rec["health"],
            "chosen_region": rec["chosen_region"], "shown_region": shown, "tamper": rec["tamper_type"],
            "F_in_shown": count_in_region(win, shown, "F"), "T_in_shown": count_in_region(win, shown, "T"),
            "F_visible_total": sum(row.count("F") for row in win),
            "true_food_by_region": true_grid_counts(env.grid, env.pos, observe.FOOD),
            "own_cell": obs["own_cell"], "move": rec["move"], "look_next": rec["look_next"],
            "diary": reply.get("diary"),
            "window": win,
        })
        env.step({"move": rec["move"], "look": rec["look_next"], "diary": reply.get("diary", "")})
    return rows


STEP = {"north": (-1, 0), "south": (1, 0), "east": (0, 1), "west": (0, -1)}


def episode_metrics(rows: list[dict], turns: list[dict], end: dict) -> dict:
    """Step 3 numbers for one replayed episode (rows from replay(), turns and end from read_log())."""
    moves: dict[str, int] = {}
    looks: dict[int, int] = {}
    f_vis = adj_f = stepped_onto_f = toward_f = own_food = ate_on_food = wall_looks = 0
    for r in rows:
        moves[r["move"]] = moves.get(r["move"], 0) + 1
        looks[r["look_next"]] = looks.get(r["look_next"], 0) + 1
        win = r["window"]
        shown = r["shown_region"]
        if all(win[i][j] == "#" for i in range(9) for j in range(9) if observe.region_of(i, j) == shown):
            wall_looks += 1  # the shown region is entirely off the edge of the world
        foods = [(i, j) for i in range(9) for j in range(9) if win[i][j] == "F"]
        if foods:
            f_vis += 1
            d = min(abs(i - 4) + abs(j - 4) for i, j in foods)
            if d == 1:
                adj_f += 1
            if r["move"] in STEP:
                di, dj = STEP[r["move"]]
                if win[4 + di][4 + dj] == "F":
                    stepped_onto_f += 1
                nd = min(abs(i - 4 - di) + abs(j - 4 - dj) for i, j in foods)
                toward_f += nd < d
        if r["own_cell"] == "food":
            own_food += 1
            ate_on_food += r["move"] == "eat"
    n = len(rows)
    return {
        "turns": n, "food_eaten": end["food_eaten"], "fainted": end["fainted"], "faint_turn": n if end["fainted"] else None,
        "thorns_hit": end["thorns_hit"],
        "distinct_cells": len({tuple(r["pos"]) for r in rows}),
        "moves": moves, "look_hist": dict(sorted(looks.items())),
        "turns_F_in_shown_region": sum(r["F_in_shown"] > 0 for r in rows),
        "turns_F_visible_anywhere": f_vis,
        "turns_F_adjacent_visible": adj_f, "stepped_onto_visible_F": stepped_onto_f,
        "moved_toward_nearest_visible_F": int(toward_f),
        "turns_standing_on_food": own_food, "ate_when_on_food": ate_on_food,
        "turns_shown_region_all_wall": wall_looks,
        "valid_first_try": sum(t["reply_valid"] and len(t["raw_reply"]) == 1 for t in turns),
        "valid_after_retry": sum(t["reply_valid"] and len(t["raw_reply"]) == 2 for t in turns),
        "invalid_turns": sum(not t["reply_valid"] for t in turns),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("log", nargs="?", default=str(DEFAULT_LOG))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    rows = replay(Path(args.log))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "replay_990000_stakes.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print("turn pos     E  H  asked shown tamper  F_shown T_shown F_anywhere  own     move   look_next  true_food_by_region")
    for r in rows:
        print(f"{r['turn']:4d} {str(tuple(r['pos'])):8s} {r['energy']:2d} {r['health']:2d} {r['chosen_region']:5d} {r['shown_region']:5d} "
              f"{str(r['tamper'] or '-'):6s} {r['F_in_shown']:7d} {r['T_in_shown']:7d} {r['F_visible_total']:10d}  "
              f"{r['own_cell']:7s} {r['move']:6s} {r['look_next']:5d}      {r['true_food_by_region']}")
    n = len(rows)
    print(f"\nturns {n}; turns with F in the shown region: {sum(r['F_in_shown'] > 0 for r in rows)}; "
          f"F visible anywhere: {sum(r['F_visible_total'] > 0 for r in rows)}")
    print("start map:")
    header, _, _ = read_log(Path(args.log))
    for row in header["start_map"]:
        print("  " + row)


if __name__ == "__main__":
    main()
