"""Shared builders for the runner tests. Every prompt and question here is a dummy marker, not study text."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from runner.config import REPO_ROOT, Config, load_config
from runner.fake_client import FakeClient, random_valid_script, valid_reply
from runner.run import Runner

QUESTION = "TEST-CHECKIN-QUESTION (a dummy marker, not the preregistered question)"
PRICE_FILE = REPO_ROOT / "runner" / "prices" / "2026-11-26.json"
TIERS = ("haiku", "sonnet", "opus")
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}


def make_config(tmp: Path, *, caps=None, priors=None, pairs=None, seed_lists=None, shuffle_seed=7, price_file=PRICE_FILE,
                max_consecutive_exclusions=3, blinded_phases=("confirmatory",), skip=()) -> Config:
    """A config whose runs_dir, prompts and seed files live under tmp. skip names files not to create."""
    (tmp / "prompts").mkdir(exist_ok=True)
    files = {"stakes": "TEST system prompt stakes", "no_stakes": "TEST system prompt no_stakes", "checkin_question": QUESTION}
    for name, text in files.items():
        if name not in skip:
            (tmp / "prompts" / f"{name}.txt").write_text(text, encoding="utf-8")
    seed_lists = seed_lists or {
        "dev": list(range(990000, 990020)), "pilot": list(range(1000, 1020)),
        "confirmatory": list(range(2000, 2020)), "reserve": list(range(3000, 3020)),
    }
    phases = {}
    for phase, seeds in seed_lists.items():
        f = tmp / f"seeds_{phase}.txt"
        if "seeds" not in skip:
            f.write_text("# test seeds\n" + "\n".join(map(str, seeds)) + "\n", encoding="utf-8")
        phases[phase] = {"seed_file": str(f), "pairs_per_tier": {t: (pairs or {}).get(t, 1) for t in TIERS}}
    raw = {
        "runs_dir": str(tmp / "runs"),
        "price_file": str(price_file),
        "models": MODELS,
        "effort": "low",
        "max_tokens": 2000,
        "caps_usd": {"dev": 10, "pilot": 100, "confirmatory": 750, "reserve": 150, **(caps or {})},
        "priors_usd": {"haiku": 0.03, "sonnet": 0.45, "opus": 0.90, **(priors or {})},
        "retry": {"max_retries": 2, "backoff_base_seconds": 2, "backoff_max_seconds": 60},
        "max_consecutive_exclusions": max_consecutive_exclusions,
        "shuffle_seed": shuffle_seed,
        "blinded_phases": list(blinded_phases),
        "prompts": {k: str(tmp / "prompts" / f"{k}.txt") for k in files},
        "phases": phases,
    }
    path = tmp / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return load_config(path)


def make_runner(cfg: Config, phase: str = "dev", script=None, *, tiers=None, limit_pairs=None, sleeps=None,
                key_path=None, lines=None) -> Runner:
    client = FakeClient(script if script is not None else random_valid_script(1))
    r = Runner(cfg, phase, client, tiers=tiers, limit_pairs=limit_pairs, progress=False,
               say=(lines.append if lines is not None else (lambda m: None)),
               sleep=(sleeps.append if sleeps is not None else (lambda s: None)), key_path=key_path, version="t")
    return r


def stay_script(**kw):
    """Always replies "stay": the stakes critter never eats and faints on turn 20."""
    return lambda kwargs: valid_reply("stay", 4, "staying", **kw)


def read_gz_lines(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def manifest(cfg: Config, phase: str = "dev") -> list[dict]:
    p = cfg.runs_dir / phase / "manifest.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def all_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []
