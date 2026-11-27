"""Price file and the append-only spend ledger.

One JSONL ledger per phase. Every API response appends one "response" line
(time, phase, model, episode id, turn, each usage count, cost). Spend so far
is the sum of the "response" lines, re-read from disk on start, so a restart
cannot forget money already spent. "episode_end" lines only mark an episode
finished (for the running mean) and are never summed into spend.

Cost is priced from a dated price file in USD per million tokens. A request's
prompt size is input + cache creation + cache read tokens; that picks the
price tier (Haiku has a cheaper tier up to 100,000 prompt tokens).
output_tokens already includes thinking tokens, so nothing extra is added.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

RATE_KEYS = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")


class PriceError(ValueError):
    pass


class LedgerError(RuntimeError):
    pass


class CapExceeded(RuntimeError):
    """Phase spend has passed the cap. The run stops at once."""

    def __init__(self, phase: str, spend: float, cap: float):
        super().__init__(f"{phase} spend ${spend:.4f} has passed the ${cap:.2f} cap")
        self.phase, self.spend, self.cap = phase, spend, cap


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0       # all cache writes
    cache_read_tokens: int = 0
    cache_creation_1h_tokens: int = 0    # the part of cache_creation_tokens written with the 1-hour TTL

    def __post_init__(self):
        for k, v in vars(self).items():
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValueError(f"usage {k} must be a non-negative integer, got {v!r}")
        if self.cache_creation_1h_tokens > self.cache_creation_tokens:
            raise ValueError("cache_creation_1h_tokens cannot exceed cache_creation_tokens")

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens


class PriceTable:
    def __init__(self, data: dict, path: Path | None = None):
        self.path = path
        self.source = data.get("source")
        self.read_on = data.get("read_on")
        if not self.source or not self.read_on:
            raise PriceError("price file must carry 'source' and 'read_on'")
        self._models: dict[str, list[tuple[float, dict]]] = {}
        for model, entry in (data.get("models") or {}).items():
            tiers = entry.get("tiers") or []
            parsed = []
            for t in tiers:
                rates = {}
                for k in RATE_KEYS:
                    v = t.get(k)
                    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                        raise PriceError(f"{model}: rate {k!r} must be a non-negative number, got {v!r}")
                    rates[k] = float(v)
                limit = t.get("max_prompt_tokens")
                parsed.append((float("inf") if limit is None else float(limit), rates))
            if not parsed or parsed[-1][0] != float("inf") or [p[0] for p in parsed] != sorted(p[0] for p in parsed):
                raise PriceError(f"{model}: tiers must be in ascending order and the last must have max_prompt_tokens null")
            self._models[model] = parsed

    @classmethod
    def load(cls, path: str | Path) -> "PriceTable":
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as e:
            raise PriceError(f"cannot read price file {path}: {e}") from e
        except ValueError as e:
            raise PriceError(f"price file {path} is not valid JSON: {e}") from e
        return cls(data, path)

    def require(self, model: str) -> None:
        if model not in self._models:
            raise PriceError(f"no price entry for model {model!r} in {self.path or 'the price file'}; refusing to run it")

    def rates(self, model: str, prompt_tokens: int) -> dict:
        self.require(model)
        for limit, rates in self._models[model]:
            if prompt_tokens <= limit:
                return rates
        raise AssertionError("unreachable: last tier is unbounded")

    def cost(self, model: str, usage: Usage) -> float:
        r = self.rates(model, usage.prompt_tokens)
        write_5m = usage.cache_creation_tokens - usage.cache_creation_1h_tokens
        return (usage.input_tokens * r["input"] + write_5m * r["cache_write_5m"]
                + usage.cache_creation_1h_tokens * r["cache_write_1h"]
                + usage.cache_read_tokens * r["cache_read"] + usage.output_tokens * r["output"]) / 1e6


@dataclass(frozen=True)
class StartCheck:
    ok: bool
    spend: float
    cap: float
    expected_cost: float
    basis: str  # "running mean" or "prior"

    def message(self) -> str:
        return (f"spend ${self.spend:.4f} + 2 x ${self.expected_cost:.4f} ({self.basis}) = "
                f"${self.spend + 2 * self.expected_cost:.4f} vs cap ${self.cap:.2f}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Ledger:
    def __init__(self, runs_dir: str | Path, phase: str, cap_usd: float, prices: PriceTable):
        self.phase, self.cap, self.prices = phase, float(cap_usd), prices
        self.path = Path(runs_dir) / "ledger" / f"{phase}.jsonl"
        self._offset = 0
        self._spend = 0.0
        self._episode_cost: dict[str, float] = {}
        self._finished: dict[str, list[float]] = {}  # model -> costs of episodes that finished (status "done")
        self._refresh(startup=True)

    # ---- reading
    def _refresh(self, startup: bool = False):
        try:
            with open(self.path, "rb") as f:
                f.seek(self._offset)
                data = f.read()
        except FileNotFoundError:
            return
        end = data.rfind(b"\n") + 1
        if startup and end != len(data):
            raise LedgerError(f"{self.path} ends in the middle of a line (a write was cut off); "
                              f"fix or move that file by hand, the runner will not guess the spend")
        for raw in data[:end].split(b"\n")[:-1]:
            self._offset += len(raw) + 1
            self._ingest(raw)

    def _ingest(self, raw: bytes):
        try:
            obj = json.loads(raw)
            kind = obj["type"]
        except (ValueError, KeyError, TypeError) as e:
            raise LedgerError(f"{self.path}: unreadable ledger line {raw[:80]!r}: {e}") from e
        if obj.get("phase") != self.phase:
            raise LedgerError(f"{self.path}: line belongs to phase {obj.get('phase')!r}, not {self.phase!r}")
        if kind == "response":
            cost = float(obj["cost_usd"])
            self._spend += cost
            self._episode_cost[obj["episode_id"]] = self._episode_cost.get(obj["episode_id"], 0.0) + cost
        elif kind == "episode_end":
            if obj["status"] == "done":
                self._finished.setdefault(obj["model"], []).append(float(obj["cost_usd"]))
        else:
            raise LedgerError(f"{self.path}: unknown line type {kind!r}")

    @property
    def spend(self) -> float:
        self._refresh()
        return self._spend

    def mean_episode_cost(self, model: str) -> float | None:
        self._refresh()
        costs = self._finished.get(model)
        return sum(costs) / len(costs) if costs else None

    # ---- the two cap rules
    def start_check(self, model: str, prior_usd: float) -> StartCheck:
        """Before an episode: refuse if spend plus twice the tier's running mean episode cost
        (its prior until the tier has a finished episode) would pass the cap."""
        mean = self.mean_episode_cost(model)
        expected, basis = (mean, "running mean") if mean is not None else (float(prior_usd), "prior")
        spend = self.spend
        return StartCheck(spend + 2 * expected <= self.cap, spend, self.cap, expected, basis)

    def check_cap(self):
        """After a response: raise CapExceeded if spend has passed the cap."""
        spend = self.spend
        if spend > self.cap:
            raise CapExceeded(self.phase, spend, self.cap)

    # ---- writing
    def _append(self, obj: dict):
        line = (json.dumps({**obj, "phase": self.phase}, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._refresh()  # pick up lines another process wrote, so the offset stays aligned
        with open(self.path, "ab") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        self._refresh()

    def record_response(self, *, model: str, episode_id: str, turn: int, usage: Usage, attempt: int = 0) -> float:
        cost = self.prices.cost(model, usage)
        self._append({
            "type": "response", "time": _now(), "model": model, "episode_id": episode_id, "turn": turn, "attempt": attempt,
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "cache_creation_input_tokens": usage.cache_creation_tokens,
            "cache_creation_1h_input_tokens": usage.cache_creation_1h_tokens,
            "cache_read_input_tokens": usage.cache_read_tokens, "cost_usd": cost,
        })
        return cost

    def episode_cost(self, episode_id: str) -> float:
        self._refresh()
        return self._episode_cost.get(episode_id, 0.0)

    def record_episode_end(self, *, model: str, episode_id: str, status: str):
        self._append({"type": "episode_end", "time": _now(), "model": model, "episode_id": episode_id,
                      "status": status, "cost_usd": self.episode_cost(episode_id)})
