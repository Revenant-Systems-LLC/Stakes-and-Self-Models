"""Runner config. Caps, priors, models and paths live here and nowhere else.

There is no command-line way to change a cap. The caps in a config file may
not exceed the preregistered ones (PREREGISTRATION.md, "Budget and hard
cap"), so even an edited config cannot raise them above the plan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "runner" / "config.json"
DEFAULT_RUNS_DIR = Path(r"M:\Projects\Lobster-Lab\runs")

PHASES = ("dev", "pilot", "confirmatory", "reserve", "tiers")
REAL_PHASES = ("pilot", "confirmatory", "reserve", "tiers")
TIERS = ("haiku", "sonnet", "opus")          # the three preregistered tiers
EXTRA_TIERS = ("fable", "mythos")            # the exploratory tiers phase
ALL_TIERS = TIERS + EXTRA_TIERS
ORDERS = ("shuffled", "alternate")
# The tiers phase takes over the $150 the reserve phase used to hold (the draft amendment drops the paid reserve).
PREREGISTERED_CAPS = {"pilot": 100.0, "confirmatory": 750.0, "reserve": 150.0, "tiers": 150.0}
DEV_SEEDS = range(990000, 990200)
EFFORTS = ("low", "medium", "high", "xhigh", "max")

_TOP_KEYS = {"runs_dir", "price_file", "models", "effort", "max_tokens", "caps_usd", "priors_usd", "retry",
             "max_consecutive_exclusions", "shuffle_seed", "blinded_phases", "prompts", "phases"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PhaseConfig:
    seed_file: Path
    pairs_per_tier: dict   # every tier in ALL_TIERS; tiers the config leaves out plan 0 pairs
    order: str = "shuffled"  # "shuffled": fixed-seed shuffle across tiers. "alternate": tier by tier, k by k, no randomness


@dataclass(frozen=True)
class Config:
    runs_dir: Path
    price_file: Path
    models: dict          # tier -> model id (the mythos id is this one value; change it here to switch Mythos versions)
    effort: str
    max_tokens: int
    caps_usd: dict        # phase -> cap
    priors_usd: dict      # tier -> prior mean episode cost
    max_retries: int
    backoff_base_seconds: float
    backoff_max_seconds: float
    max_consecutive_exclusions: int
    shuffle_seed: int
    blinded_phases: tuple
    prompt_files: dict    # "stakes" | "no_stakes" | "checkin_question" -> path
    phases: dict          # phase -> PhaseConfig
    source: Path

    def tier_of(self, model: str) -> str:
        for tier, m in self.models.items():
            if m == model:
                return tier
        raise ConfigError(f"model {model!r} is not one of the configured models {sorted(self.models.values())}")


def _path(value, base: Path = REPO_ROOT) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (base / p)


def _need(raw: dict, key: str, where: str = "config"):
    if key not in raw:
        raise ConfigError(f"{where} is missing {key!r}")
    return raw[key]


def _number(value, what: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise ConfigError(f"{what} must be a number >= {minimum}, got {value!r}")
    return float(value)


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path is not None else DEFAULT_CONFIG
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ConfigError(f"cannot read config file {path}: {e}") from e
    except ValueError as e:
        raise ConfigError(f"config file {path} is not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"config file {path} must hold a JSON object")
    unknown = set(raw) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"unknown config keys {sorted(unknown)} (typo?)")

    runs_dir = _path(raw.get("runs_dir", DEFAULT_RUNS_DIR)).resolve()
    if runs_dir == REPO_ROOT or REPO_ROOT in runs_dir.parents:
        raise ConfigError(f"runs_dir must be outside the repository, got {runs_dir}")

    models = dict(_need(raw, "models"))
    if set(models) != set(ALL_TIERS) or not all(isinstance(m, str) and m for m in models.values()):
        raise ConfigError(f"models must map exactly {list(ALL_TIERS)} to model id strings")
    effort = raw.get("effort", "low")
    if effort not in EFFORTS:
        raise ConfigError(f"effort must be one of {EFFORTS}")
    max_tokens = int(_number(raw.get("max_tokens", 2000), "max_tokens", minimum=1))

    caps = {p: _number(v, f"caps_usd.{p}") for p, v in _need(raw, "caps_usd").items()}
    for p in PHASES:
        if p not in caps:
            raise ConfigError(f"caps_usd is missing phase {p!r}")
    extra = set(caps) - set(PHASES)
    if extra:
        raise ConfigError(f"caps_usd has unknown phases {sorted(extra)}")
    for p, ceiling in PREREGISTERED_CAPS.items():
        if caps[p] > ceiling:
            raise ConfigError(f"caps_usd.{p} is {caps[p]} but the preregistered cap is {ceiling}; a cap cannot be raised here")

    priors = {t: _number(v, f"priors_usd.{t}") for t, v in _need(raw, "priors_usd").items()}
    if set(priors) != set(ALL_TIERS):
        raise ConfigError(f"priors_usd must cover exactly {list(ALL_TIERS)}")

    retry = raw.get("retry", {})
    prompts = dict(_need(raw, "prompts"))
    if set(prompts) != {"stakes", "no_stakes", "checkin_question"}:
        raise ConfigError("prompts must name stakes, no_stakes and checkin_question files")

    phases = {}
    for name, ph in _need(raw, "phases").items():
        if name not in PHASES:
            raise ConfigError(f"unknown phase {name!r}")
        counts = {t: int(_number(n, f"phases.{name}.pairs_per_tier.{t}")) for t, n in _need(ph, "pairs_per_tier", f"phases.{name}").items()}
        if not set(counts) <= set(ALL_TIERS):
            raise ConfigError(f"phases.{name}.pairs_per_tier has unknown tiers {sorted(set(counts) - set(ALL_TIERS))} (typo?)")
        counts = {t: counts.get(t, 0) for t in ALL_TIERS}
        order = ph.get("order", "shuffled")
        if order not in ORDERS:
            raise ConfigError(f"phases.{name}.order must be one of {ORDERS}, got {order!r}")
        phases[name] = PhaseConfig(_path(_need(ph, "seed_file", f"phases.{name}")), counts, order)
    blinded = tuple(raw.get("blinded_phases", ["confirmatory"]))
    if not set(blinded) <= set(PHASES):
        raise ConfigError("blinded_phases has an unknown phase")

    return Config(
        runs_dir=runs_dir,
        price_file=_path(_need(raw, "price_file")),
        models=models,
        effort=effort,
        max_tokens=max_tokens,
        caps_usd=caps,
        priors_usd=priors,
        max_retries=int(_number(retry.get("max_retries", 5), "retry.max_retries")),
        backoff_base_seconds=_number(retry.get("backoff_base_seconds", 2), "retry.backoff_base_seconds"),
        backoff_max_seconds=_number(retry.get("backoff_max_seconds", 60), "retry.backoff_max_seconds"),
        max_consecutive_exclusions=int(_number(raw.get("max_consecutive_exclusions", 3), "max_consecutive_exclusions", minimum=1)),
        shuffle_seed=int(_number(_need(raw, "shuffle_seed"), "shuffle_seed")),
        blinded_phases=blinded,
        prompt_files={k: _path(v) for k, v in prompts.items()},
        phases=phases,
        source=path,
    )


def read_text_file(path: Path, what: str) -> str:
    """A prompt or question file named by the config. Missing or empty is a clear error."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"{what} file is missing: {path}. The runner does not write prompt or question text; "
                          f"put the file there or point the config at it.") from None
    except OSError as e:
        raise ConfigError(f"cannot read {what} file {path}: {e}") from e
    if not text.strip():
        raise ConfigError(f"{what} file is empty: {path}")
    return text
