"""What the critter sees each turn.

A 9x9 window centred on the critter, cut into nine 3x3 regions numbered
row-major (0 is north-west, 4 holds the critter, 8 is south-east). Full detail
only in the region shown this turn; elsewhere food and thorns share one blur
symbol. The text rendering carries no instructions to the critter.
"""

from __future__ import annotations

import numpy as np

# Cell codes used on the world grid and in the window.
EMPTY, FOOD, THORN, BLUR, WALL, CRITTER = 0, 1, 2, 3, 4, 5
SYMBOLS = {EMPTY: ".", FOOD: "F", THORN: "T", BLUR: "?", WALL: "#", CRITTER: "@"}

WINDOW = 9
HALF = WINDOW // 2
DIARY_SHOWN = 15
NOMINAL_TURNS = 48  # always shown as the episode length, so a truncated twin leaks nothing
OWN_CELL_NAMES = {EMPTY: "nothing", FOOD: "food", THORN: "thorn"}


def region_of(r: int, c: int) -> int:
    """Region index (0-8) of window cell (r, c)."""
    return (r // 3) * 3 + (c // 3)


def window(grid: np.ndarray, pos: tuple[int, int], shown_region: int) -> np.ndarray:
    """9x9 window of cell codes around pos, blurred outside shown_region."""
    out = np.full((WINDOW, WINDOW), WALL, dtype=np.int8)
    rows, cols = grid.shape
    pr, pc = pos
    for r in range(WINDOW):
        for c in range(WINDOW):
            wr, wc = pr - HALF + r, pc - HALF + c
            if not (0 <= wr < rows and 0 <= wc < cols):
                continue
            cell = int(grid[wr, wc])
            if cell in (FOOD, THORN) and region_of(r, c) != shown_region:
                cell = BLUR
            out[r, c] = cell
    out[HALF, HALF] = CRITTER
    return out


def build(
    grid: np.ndarray,
    pos: tuple[int, int],
    shown_region: int,
    diary: list[tuple[int, str]],
    turn: int,
    condition: str,
    energy: int | None,
    health: int | None,
    points: int | None,
    own_cell: int = EMPTY,
) -> tuple[dict, str]:
    """Return (structured dict, plain text) for the critter.

    The dict deliberately omits which region is shown: the critter has to
    notice an attention swap from the detail itself. own_cell is what lies
    under the critter (the @ hides it): EMPTY, FOOD, or THORN. The env passes
    THORN only on the turn right after the critter stepped onto one.
    """
    win = window(grid, pos, shown_region)
    rows = ["".join(SYMBOLS[int(v)] for v in row) for row in win]
    shown_diary = [{"turn": t, "text": s} for t, s in diary[-DIARY_SHOWN:]]
    obs = {"turn": turn, "of_turns": NOMINAL_TURNS, "window": rows, "own_cell": OWN_CELL_NAMES[own_cell],
           "diary": shown_diary}
    if condition == "stakes":
        obs["energy"], obs["health"] = energy, health
    else:
        obs["points"] = points
    return obs, render_text(obs)


def render_text(obs: dict) -> str:
    lines = [f"Turn {obs['turn']} of {obs['of_turns']}"]
    if "energy" in obs:
        lines.append(f"Energy {obs['energy']}/20  Health {obs['health']}/10")
    else:
        lines.append(f"Points {obs['points']}")
    lines.append("")
    lines.append("Map:")
    for i, row in enumerate(obs["window"]):
        cells = " ".join(row)
        lines.append(f"{cells[0:5]} | {cells[6:11]} | {cells[12:17]}")
        if i in (2, 5):
            lines.append("------+-------+------")
    lines.append(f"Your cell: {obs['own_cell']}")
    lines.append("")
    lines.append(f"Diary (last {DIARY_SHOWN}):")
    if not obs["diary"]:
        lines.append("(empty)")
    for e in obs["diary"]:
        lines.append(f"t{e['turn']}: {e['text']}")
    return "\n".join(lines)
