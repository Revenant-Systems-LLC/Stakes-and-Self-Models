"""Sprite manifest: the slot David's original art drops into.

The manifest is a JSON file next to the art (default viewer/static/art/manifest.json).
It names every animation clip the viewer needs, where each clip's frames sit on a
sprite sheet, how long each frame shows, and where the art came from. static/anim.js
reads clip lengths and frame timing from it; renderer.js will read the sheets from it
once the visual pass wires that in. Until then the manifest says "source": "procedural"
and the viewer keeps drawing the current pixel art from static/sprites.js.

Check a manifest before committing new art:

    python -m viewer.manifest                       # the default manifest
    python -m viewer.manifest path/to/manifest.json

It prints every problem and exits 1 if there are any. The format is in
viewer/docs/animation.md.

Clean-room rule, enforced here: every sprite sheet needs a "provenance" line saying
who drew it and from what (for example "drawn by David Fisher from clip 03, his own
footage"). A sheet without one fails the check, so art of unknown origin can't slip in.
"""

from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

FORMAT = "clawlings-sprites"
VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parent / "static" / "art" / "manifest.json"
ANIM_JS = Path(__file__).resolve().parent / "static" / "anim.js"

# Kept in step with CLIPS, ONE_SHOT and EMOTES in static/anim.js; a test checks they match.
REQUIRED_CLIPS = (
    "idle", "idle_happy", "idle_worried", "idle_hurt",
    "walk_north", "walk_south", "walk_east", "walk_west",
    "eat", "ouch", "think", "faint", "sleep",
)
ONE_SHOT = ("eat", "ouch", "think", "faint")
REQUIRED_EMOTES = ("heart", "alert", "swap", "question", "pencil", "zzz", "dots", "sweat")
SOURCES = ("procedural", "sheets")
MAX_FRAME_MS = 5000

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-./]+$")


def png_size(path: Path) -> tuple[int, int] | None:
    """Width and height from a PNG's header, or None if it isn't a PNG."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def _pair(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in v)


def _check_ms(where: str, entry: dict, n: int, problems: list[str]):
    ms = entry.get("ms")
    if isinstance(ms, bool) or ms is None:
        problems.append(f"{where}: ms is missing (one number for every frame, or a list with one per frame)")
    elif isinstance(ms, int):
        if not 0 < ms <= MAX_FRAME_MS:
            problems.append(f"{where}: ms {ms} is out of range (1 to {MAX_FRAME_MS})")
    elif isinstance(ms, list):
        if len(ms) != n:
            problems.append(f"{where}: ms has {len(ms)} entries for {n} frames")
        elif not all(isinstance(x, int) and not isinstance(x, bool) and 0 < x <= MAX_FRAME_MS for x in ms):
            problems.append(f"{where}: every ms entry must be a whole number from 1 to {MAX_FRAME_MS}")
    else:
        problems.append(f"{where}: ms must be a number or a list of numbers")


def _check_safe_path(where: str, rel, problems: list[str]) -> bool:
    if not isinstance(rel, str) or not rel:
        problems.append(f"{where}: image path is missing")
        return False
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts or rel.startswith(("/", "\\")) or not _SAFE_NAME.match(rel):
        problems.append(f"{where}: image path {rel!r} must be a plain relative path inside the art folder")
        return False
    if p.suffix.lower() != ".png":
        problems.append(f"{where}: image {rel!r} must be a .png")
        return False
    return True


def _check_entry(kind: str, name: str, entry, m: dict, base: Path, sizes: dict, problems: list[str], *, check_files: bool):
    where = f"{kind} {name!r}"
    if not isinstance(entry, dict):
        problems.append(f"{where}: must be an object")
        return
    if "mirror" in entry:
        target = entry["mirror"]
        pool = m.get("clips" if kind == "clip" else "emotes") or {}
        if target == name or target not in pool:
            problems.append(f"{where}: mirrors {target!r}, which isn't in the manifest")
        elif isinstance(pool[target], dict) and "mirror" in pool[target]:
            problems.append(f"{where}: mirrors {target!r}, which is itself a mirror")
        extra = set(entry) - {"mirror", "note"}
        if extra:
            problems.append(f"{where}: a mirror takes only 'mirror' (and an optional note), not {sorted(extra)}")
        return
    source = m.get("source")
    frames = entry.get("frames")
    if source == "procedural":
        if not isinstance(frames, int) or isinstance(frames, bool) or frames < 1:
            problems.append(f"{where}: with source 'procedural', frames is a count of 1 or more")
            return
        n = frames
    else:
        if not isinstance(frames, list) or not frames or not all(_pair(f) and f[0] >= 0 and f[1] >= 0 for f in frames):
            problems.append(f"{where}: frames must be a list of [column, row] cells on its sheet")
            return
        n = len(frames)
        sheet = entry.get("sheet")
        sheets = m.get("sheets") or {}
        if sheet not in sheets:
            problems.append(f"{where}: sheet {sheet!r} isn't listed under sheets")
        elif check_files and sizes.get(sheet):
            cw, ch = m["cell"]
            w, h = sizes[sheet]
            for col, row in frames:
                if (col + 1) * cw > w or (row + 1) * ch > h:
                    problems.append(f"{where}: cell [{col}, {row}] runs past the edge of {sheets[sheet].get('image')} ({w}x{h})")
                    break
    _check_ms(where, entry, n, problems)
    loop = entry.get("loop")
    if not isinstance(loop, bool):
        problems.append(f"{where}: loop must be true or false")
    elif kind == "clip" and name in REQUIRED_CLIPS:
        if name in ONE_SHOT and loop:
            problems.append(f"{where}: plays once, so loop must be false")
        if name not in ONE_SHOT and not loop:
            problems.append(f"{where}: repeats, so loop must be true")


def check(m, base: Path | None = None, *, check_files: bool = True) -> list[str]:
    """Every problem with a manifest, as plain sentences. An empty list means it's good."""
    problems: list[str] = []
    if not isinstance(m, dict):
        return ["the manifest must be a JSON object"]
    base = Path(base) if base else DEFAULT_PATH.parent
    if m.get("format") != FORMAT:
        problems.append(f"format must be {FORMAT!r}")
    if m.get("version") != VERSION:
        problems.append(f"version must be {VERSION}")
    source = m.get("source")
    if source not in SOURCES:
        problems.append(f"source must be one of {list(SOURCES)}")
    cell = m.get("cell")
    if not (_pair(cell) and cell[0] > 0 and cell[1] > 0):
        problems.append("cell must be [width, height] in pixels")
        cell = None
    anchor = m.get("anchor")
    if not _pair(anchor):
        problems.append("anchor must be [x, y]: where the tile's top-left corner sits inside a cell")
    elif cell and not (0 <= anchor[0] < cell[0] and 0 <= anchor[1] < cell[1]):
        problems.append(f"anchor {anchor} is outside the {cell[0]}x{cell[1]} cell")

    sizes: dict[str, tuple[int, int] | None] = {}
    sheets = m.get("sheets") or {}
    if not isinstance(sheets, dict):
        problems.append("sheets must be an object")
        sheets = {}
    if source == "sheets" and not sheets:
        problems.append("source is 'sheets' but no sheets are listed")
    for sname, sheet in sheets.items():
        where = f"sheet {sname!r}"
        if not isinstance(sheet, dict):
            problems.append(f"{where}: must be an object")
            continue
        prov = sheet.get("provenance")
        if not isinstance(prov, str) or len(prov.strip()) < 10:
            problems.append(f"{where}: needs a provenance line saying who drew it and from what")
        if not _check_safe_path(where, sheet.get("image"), problems) or not check_files:
            continue
        f = base / sheet["image"]
        if not f.is_file():
            problems.append(f"{where}: {sheet['image']} isn't in {base}")
            continue
        size = png_size(f)
        if size is None:
            problems.append(f"{where}: {sheet['image']} isn't a readable PNG")
        elif cell and (size[0] % cell[0] or size[1] % cell[1]):
            problems.append(f"{where}: {sheet['image']} is {size[0]}x{size[1]}, not a whole number of {cell[0]}x{cell[1]} cells")
        sizes[sname] = size if cell else None

    if cell is None:
        return problems
    for kind, key, required in (("clip", "clips", REQUIRED_CLIPS), ("emote", "emotes", REQUIRED_EMOTES)):
        pool = m.get(key)
        if not isinstance(pool, dict):
            problems.append(f"{key} must be an object")
            continue
        for name in required:
            if name not in pool:
                problems.append(f"{kind} {name!r} is missing")
        for name, entry in pool.items():
            if name not in required:
                problems.append(f"{kind} {name!r} isn't one the viewer uses (check the spelling)")
            _check_entry(kind, name, entry, m, base, sizes, problems, check_files=check_files)
    return problems


def load(path: str | Path = DEFAULT_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clip_ms(m: dict, name: str, pool: str = "clips") -> int:
    """Total length of one pass through a clip, following a mirror."""
    entry = m[pool][name]
    if "mirror" in entry:
        entry = m[pool][entry["mirror"]]
    n = entry["frames"] if isinstance(entry["frames"], int) else len(entry["frames"])
    ms = entry["ms"]
    return sum(ms) if isinstance(ms, list) else ms * n


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else DEFAULT_PATH
    try:
        m = load(path)
    except (OSError, ValueError) as e:
        print(f"can't read {path}: {e}")
        return 1
    problems = check(m, path.parent)
    if problems:
        print(f"{path}: {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"{path}: ok ({m['source']}, {len(m['clips'])} clips, {len(m['emotes'])} emotes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
