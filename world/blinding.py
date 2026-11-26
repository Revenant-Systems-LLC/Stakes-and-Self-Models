"""Blinded condition codes for confirmatory runs.

A key file kept outside the repository maps "stakes" and "no_stakes" to two
random codes. It is created once, the first time it is needed, and never
overwritten. Blinded logs carry the code; pilot logs (blinded=False) carry
the plain condition name.

The key path defaults to DEFAULT_KEY_PATH and can be set per call or with the
STAKES_BLINDING_KEY environment variable. A path inside the repository is
refused, so the key can never be committed.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from world.env import CONDITIONS

DEFAULT_KEY_PATH = Path(r"M:\Projects\Lobster-Lab\blinding_key.json")
ENV_VAR = "STAKES_BLINDING_KEY"
REPO_ROOT = Path(__file__).resolve().parent.parent
_ALPHABET = "ABCDEFGHJKMNPQRTUVWXYZ2346789"  # no S, O, I, L, 0, 1, 5: codes can't spell a condition name


def key_path(path: str | Path | None = None) -> Path:
    """Resolve the key path and refuse anything inside the repository."""
    p = Path(path) if path is not None else Path(os.environ.get(ENV_VAR) or DEFAULT_KEY_PATH)
    p = p.resolve()
    if p == REPO_ROOT or REPO_ROOT in p.parents:
        raise ValueError(f"blinding key must live outside the repository, got {p}")
    return p


def _new_code() -> str:
    return "C-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def _check(key: dict, p: Path) -> dict:
    if set(key) != set(CONDITIONS) or key["stakes"] == key["no_stakes"]:
        raise ValueError(f"blinding key at {p} is malformed")
    for code in key.values():
        if not isinstance(code, str) or not code or any(name in code.lower() for name in CONDITIONS):
            raise ValueError(f"blinding key at {p} has a bad code")
    return key


def load_key(path: str | Path | None = None) -> dict:
    """Return {condition: code}, creating the key file if it is missing."""
    p = key_path(path)
    if not p.exists():
        a = _new_code()
        b = _new_code()
        while b == a:
            b = _new_code()
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(p, "x", encoding="utf-8") as f:  # "x": never overwrite an existing key
                json.dump({"stakes": a, "no_stakes": b}, f, indent=2)
        except FileExistsError:
            pass  # another process created it first; use theirs
    with open(p, encoding="utf-8") as f:
        return _check(json.load(f), p)


def condition_code(condition: str, *, blinded: bool, path: str | Path | None = None) -> str:
    """The label a log header carries for this condition."""
    if condition not in CONDITIONS:
        raise ValueError(f"condition must be one of {CONDITIONS}")
    if not blinded:
        return condition
    return load_key(path)[condition]
