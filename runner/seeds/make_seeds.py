"""Rebuild the real-phase seed lists from one fixed generator seed. Standard library only.

    python runner/seeds/make_seeds.py            write the four files (refuses if any already exists)
    python runner/seeds/make_seeds.py --check    compare the files on disk with what the generator makes

Candidate i is the first 8 bytes of sha256("<GENERATOR_SEED>:<i>") taken mod the range, so the lists do not
depend on the Python version or on any random-number library. A candidate that repeats or that falls in
dev.txt is skipped. The files are cut from one stream in the order of SIZES, which is why no seed repeats
within a file or across files.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

GENERATOR_SEED = 20261127
LOW, HIGH = 1_000_000, 100_000_000          # LOW is above the dev range (990000 to 990199)
SIZES = {"pilot": 40, "confirmatory": 1300, "reserve": 200, "tiers": 150}   # drawn in this order
HERE = Path(__file__).resolve().parent


def read_ints(path: Path) -> list[int]:
    return [int(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def generate(generator_seed: int = GENERATOR_SEED, dev: set | None = None) -> dict[str, list[int]]:
    if dev is None:
        dev = set(read_ints(HERE / "dev.txt"))
    used, stream, i = set(dev), [], 0
    total = sum(SIZES.values())
    while len(stream) < total:
        n = int.from_bytes(hashlib.sha256(f"{generator_seed}:{i}".encode("ascii")).digest()[:8], "big") % (HIGH - LOW) + LOW
        i += 1
        if n not in used:
            used.add(n)
            stream.append(n)
    out, at = {}, 0
    for name, size in SIZES.items():
        out[name] = stream[at:at + size]
        at += size
    return out


def main(argv: list[str]) -> int:
    lists = generate()
    paths = {name: HERE / f"{name}.txt" for name in lists}
    if "--check" in argv:
        bad = [p.name for name, p in paths.items() if not p.exists() or read_ints(p) != lists[name]]
        print("seed files match the generator" if not bad else f"seed files differ from the generator: {bad}")
        return 1 if bad else 0
    existing = [p.name for p in paths.values() if p.exists()]
    if existing:
        print(f"refusing to overwrite {existing}; use --check to compare", file=sys.stderr)
        return 2
    for name, p in paths.items():
        p.write_text("".join(f"{s}\n" for s in lists[name]), encoding="utf-8")
        print(f"wrote {p.name}: {len(lists[name])} seeds")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
