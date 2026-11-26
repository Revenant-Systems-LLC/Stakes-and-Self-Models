"""One gzipped JSON Lines file per episode.

Line 1 is the header. Then one line per turn. A final "end" line records how
the episode finished, so a crashed run (no end line) is easy to spot.
"""

from __future__ import annotations

import gzip
import json
import subprocess
from pathlib import Path

HEADER_FIELDS = ("code_version", "arm", "model", "condition_code", "world_seed", "start_map")
TURN_FIELDS = (
    "turn", "position", "move", "chosen_region", "shown_region", "energy", "health", "points",
    "diary", "tamper", "tamper_type", "raw_reply", "checkin", "checkin_answer",
    "tokens_in", "tokens_out", "cost_usd",
)


def code_version() -> str:
    """Current git commit hash, with "-dirty" if the work tree has changes."""
    root = Path(__file__).resolve().parent.parent
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return head + ("-dirty" if dirty else "")


class EpisodeLog:
    def __init__(self, path: str | Path, *, arm: str, model: str, condition_code: str, world_seed: int,
                 start_map: list[str], version: str | None = None, extra: dict | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = gzip.open(self.path, "wt", encoding="utf-8")
        header = {
            "type": "header",
            "code_version": version if version is not None else code_version(),
            "arm": arm,
            "model": model,
            "condition_code": condition_code,
            "world_seed": world_seed,
            "start_map": start_map,
        }
        if extra:
            header.update(extra)
        self._write(header)

    def _write(self, obj: dict):
        self._f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def turn(self, record: dict):
        missing = [k for k in TURN_FIELDS if k not in record]
        if missing:
            raise ValueError(f"turn record missing {missing}")
        self._write({"type": "turn", **record})

    def end(self, summary: dict):
        self._write({"type": "end", **summary})

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read_log(path: str | Path) -> tuple[dict, list[dict], dict | None]:
    header, turns, end = None, [], None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            kind = obj.get("type")
            if kind == "header":
                header = obj
            elif kind == "turn":
                turns.append(obj)
            elif kind == "end":
                end = obj
    return header, turns, end
