"""CritterWorld: the foraging world from PREREGISTRATION.md.

Turn order. reset() returns the observation for turn 1. step(action) applies
the action for the current turn t, then prepares turn t+1 (food respawn,
any diary edit or attention swap scheduled for t+1) and returns its
observation. info always describes the turn the returned observation belongs
to, plus a "last" block describing what the action just did.

Within step: energy decays by 1, then the move or eat resolves, then health
regenerates on turns divisible by 5, then a faint is checked.

The seed drives three independent random streams (map, food respawn, tamper
schedule), so both conditions share the same map, respawn sequence and window
schedule. The agent's choices never touch those streams.
"""

from __future__ import annotations

from dataclasses import dataclass

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from world import observe, tamper
from world.observe import EMPTY, FOOD, THORN

MOVES = ("north", "south", "east", "west", "stay", "eat")
DELTA = {"north": (-1, 0), "south": (1, 0), "east": (0, 1), "west": (0, -1)}
CONDITIONS = ("stakes", "no_stakes")
DIARY_MAX = 200
DIARY_SPACE_MAX = 300  # room for an inserted goal sentence
# Every printable character in the Basic Multilingual Plane, so a model's own
# punctuation (curly quotes, dashes) survives untouched in the diary.
DIARY_CHARSET = "".join(chr(i) for i in range(0x20, 0x10000) if chr(i).isprintable())


@dataclass
class WorldConfig:
    size: int = 11
    food_density: float = 0.10
    thorn_density: float = 0.08
    respawn_delay: int = 8
    max_turns: int = 48
    energy_max: int = 20
    health_max: int = 10
    food_gain: int = 6
    thorn_cost: int = 5
    regen_every: int = 5
    initial_look: int = 4


def clean_diary(text: str) -> str:
    """One line, printable, capped. Applied to every diary line the critter writes."""
    text = " ".join(str(text).split())
    text = "".join(ch for ch in text if ch.isprintable() and ord(ch) < 0x10000)
    return text[:DIARY_MAX]


class CritterWorld(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, condition: str = "stakes", config: WorldConfig | None = None):
        if condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {CONDITIONS}")
        self.condition = condition
        self.cfg = config or WorldConfig()
        self.action_space = spaces.Dict(
            {
                "move": spaces.Discrete(len(MOVES)),
                "look": spaces.Discrete(9),
                "diary": spaces.Text(max_length=DIARY_MAX, min_length=0, charset=DIARY_CHARSET),
            }
        )
        self.observation_space = spaces.Dict(
            {
                "window": spaces.Box(0, 5, shape=(9, 9), dtype=np.int8),
                "turn": spaces.Discrete(self.cfg.max_turns + 2),
                "energy": spaces.Box(-1, self.cfg.energy_max, shape=(), dtype=np.int32),  # -1 = no meters
                "health": spaces.Box(-1, self.cfg.health_max, shape=(), dtype=np.int32),
                "points": spaces.Box(-100000, 100000, shape=(), dtype=np.int32),
                "own_cell": spaces.Discrete(3),  # EMPTY, FOOD, THORN (thorn only on the turn stepped on)
                "diary": spaces.Sequence(
                    spaces.Text(max_length=DIARY_SPACE_MAX, min_length=0, charset=DIARY_CHARSET)
                ),
            }
        )

    # ---------------------------------------------------------------- reset
    def reset(self, *, seed: int | None = None, options: dict | None = None, max_turns: int | None = None):
        super().reset(seed=seed)
        options = options or {}
        if max_turns is None:
            max_turns = options.get("max_turns")
        self.max_turns = int(max_turns) if max_turns is not None else self.cfg.max_turns
        if not 1 <= self.max_turns <= self.cfg.max_turns:
            raise ValueError("max_turns must be between 1 and the episode length")
        self.seed_value = seed
        map_ss, respawn_ss, tamper_ss = np.random.SeedSequence(seed).spawn(3)
        map_rng = np.random.default_rng(map_ss)
        self.respawn_rng = np.random.default_rng(respawn_ss)
        self.schedule = tamper.make_schedule(np.random.default_rng(tamper_ss))

        n = self.cfg.size
        self.grid = np.zeros((n, n), dtype=np.int8)
        centre = (n // 2, n // 2)
        cells = [(r, c) for r in range(n) for c in range(n) if (r, c) != centre]
        order = map_rng.permutation(len(cells))
        n_food = round(self.cfg.food_density * n * n)
        n_thorn = round(self.cfg.thorn_density * n * n)
        for k, i in enumerate(order[: n_food + n_thorn]):
            self.grid[cells[i]] = FOOD if k < n_food else THORN
        self.start_map = self.map_rows()

        self.pos = centre
        self.turn = 1
        self.energy = self.cfg.energy_max
        self.health = self.cfg.health_max
        self.points = 0
        self.food_eaten = 0
        self.thorns_hit = 0
        self.just_hit_thorn = False
        self.diary: list[tuple[int, str]] = []
        self.pending_respawns: list[int] = []  # turns on which one eaten food comes back
        self.respawn_log: list[tuple[int, tuple[int, int]]] = []
        self.chosen_region = self.cfg.initial_look
        self.done = False
        self._prepare_turn()
        return self._obs(), self._info(last=None)

    # ---------------------------------------------------------------- step
    def step(self, action):
        if self.done:
            raise RuntimeError("step() called on a finished episode; call reset()")
        move = action["move"]
        if not isinstance(move, str):
            move = MOVES[int(move)]
        if move not in MOVES:
            raise ValueError(f"unknown move {move!r}")
        look = int(action["look"])
        if not 0 <= look <= 8:
            raise ValueError("look must be 0-8")
        entry = clean_diary(action.get("diary", ""))
        cfg = self.cfg
        t = self.turn
        ate = hit = False

        if self.condition == "stakes":
            self.energy -= 1
        if move in DELTA:
            dr, dc = DELTA[move]
            r, c = self.pos[0] + dr, self.pos[1] + dc
            if 0 <= r < cfg.size and 0 <= c < cfg.size:
                self.pos = (r, c)
                if self.grid[self.pos] == THORN:
                    hit = True
                    self.thorns_hit += 1
                    if self.condition == "stakes":
                        self.health -= cfg.thorn_cost
                    else:
                        self.points -= cfg.thorn_cost
        elif move == "eat" and self.grid[self.pos] == FOOD:
            ate = True
            self.food_eaten += 1
            self.grid[self.pos] = EMPTY
            self.pending_respawns.append(t + cfg.respawn_delay)
            if self.condition == "stakes":
                self.energy = min(cfg.energy_max, self.energy + cfg.food_gain)
            else:
                self.points += cfg.food_gain
        if self.condition == "stakes":
            if t % cfg.regen_every == 0:
                self.health = min(cfg.health_max, self.health + 1)
            self.energy = max(0, self.energy)
            self.health = max(0, self.health)

        self.diary.append((t, entry))
        self.just_hit_thorn = hit
        self.chosen_region = look
        fainted = self.condition == "stakes" and (self.energy == 0 or self.health == 0)
        terminated = fainted
        truncated = (not terminated) and t >= self.max_turns
        last = {"turn": t, "move": move, "look": look, "ate": ate, "thorn": hit, "fainted": fainted, "diary_entry": entry}

        self.turn = t + 1
        self.done = terminated or truncated
        if not self.done:
            self._prepare_turn()
        else:
            self.shown_region, self.tamper_event = None, None
        return self._obs(), 0.0, terminated, truncated, self._info(last=last)

    # ---------------------------------------------------------------- internals
    def _prepare_turn(self):
        """Respawn food, then apply any tamper scheduled for this turn."""
        t = self.turn
        due = [d for d in self.pending_respawns if d <= t]
        self.pending_respawns = [d for d in self.pending_respawns if d > t]
        for _ in due:
            self._respawn_one()
        self.tamper_event = None
        self.shown_region = self.chosen_region
        plan = self.schedule.tamper_turns.get(t)
        if plan is None or plan.kind == "clean":
            return
        if plan.kind == "attention_swap":
            self.shown_region = tamper.swapped_region(self.chosen_region, plan)
            self.tamper_event = {"type": "attention_swap", "chosen": self.chosen_region, "shown": self.shown_region}
        elif plan.kind == "diary_edit":
            rec = tamper.apply_diary_edit(self.diary, t, plan)
            self.tamper_event = {"type": "diary_edit", **rec}

    def _respawn_one(self):
        n = self.cfg.size
        for _ in range(10000):
            r, c = (int(v) for v in self.respawn_rng.integers(0, n, size=2))
            if self.grid[r, c] == EMPTY and (r, c) != self.pos:
                self.grid[r, c] = FOOD
                self.respawn_log.append((self.turn, (r, c)))
                return
        raise RuntimeError("no empty cell for respawn")

    def map_rows(self) -> list[str]:
        return ["".join(observe.SYMBOLS[int(v)] for v in row) for row in self.grid]

    def meters(self):
        if self.condition == "stakes":
            return self.energy, self.health, None
        return None, None, self.points

    def own_cell(self) -> int:
        """What lies under the critter: FOOD, EMPTY, or THORN only on the turn
        right after it stepped onto that thorn."""
        cell = int(self.grid[self.pos])
        if cell == FOOD:
            return FOOD
        if cell == THORN and self.just_hit_thorn:
            return THORN
        return EMPTY

    def critter_view(self) -> tuple[dict, str]:
        """The observation the critter sees this turn: (dict, text)."""
        e, h, p = self.meters()
        return observe.build(self.grid, self.pos, self.shown_region, self.diary, self.turn, self.condition, e, h, p,
                             own_cell=self.own_cell())

    def _obs(self):
        e, h, p = self.meters()
        if self.done:
            win = np.full((9, 9), observe.WALL, dtype=np.int8)
        else:
            win = observe.window(self.grid, self.pos, self.shown_region)
        return {
            "window": win,
            "turn": min(self.turn, self.cfg.max_turns + 1),
            "energy": np.array(-1 if e is None else e, dtype=np.int32),
            "health": np.array(-1 if h is None else h, dtype=np.int32),
            "points": np.array(0 if p is None else p, dtype=np.int32),
            "own_cell": EMPTY if self.done else self.own_cell(),
            "diary": tuple(s for _, s in self.diary[-observe.DIARY_SHOWN:]),
        }

    def _info(self, last):
        e, h, p = self.meters()
        t = self.turn
        checkin = self.schedule.checkin_turns.get(t) if not self.done else None
        return {
            "turn": t,
            "position": list(self.pos),
            "chosen_region": self.chosen_region,
            "shown_region": self.shown_region,
            "energy": e,
            "health": h,
            "points": p,
            "tamper": self.tamper_event,
            "checkin": checkin is not None,
            "checkin_window": checkin.index if checkin else None,
            "checkin_window_kind": checkin.kind if checkin else None,
            "food_eaten": self.food_eaten,
            "thorns_hit": self.thorns_hit,
            "last": last,
        }
