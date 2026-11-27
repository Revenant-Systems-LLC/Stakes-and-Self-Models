"""Scripted dry run of the whole harness, before the API pilot (job 016, Amendment 1).

    python -m runner.dryrun [--out DIR] [--pairs 10] [--blinded-pairs 2] [--no-progress]
    python -m runner.dryrun --faulted-copy LOG DST_DIR

The scripted agents of world/agents.py (GreedyAgent, RandomAgent) play full twin pairs through the runner's own
play path (runner/play.play_episode), with the real world, the real check-in question from
prompts/checkin_question.txt, the answer field, twin matching (the no-stakes twin ends on the turn its stakes twin
ended), logging and blinding. No model is called and no API client is built: this file never imports one.

Seeds come from runner/seeds/dev.txt only. The first --pairs seeds are played unblinded, per agent, into
OUT/logs/scripted-greedy/ and OUT/logs/scripted-random/. The next --blinded-pairs seeds are played blinded into
OUT/logs/blinded-scripted-greedy/ and OUT/logs/blinded-scripted-random/, with a scratch blinding key at
OUT/blinding_key.json (never the real key, never inside the repository).

Nothing here touches the real ledger or manifest (no Ledger or Manifest is built), deletes anything, or overwrites
anything: if a group folder already holds logs the run refuses to start, and --out names a fresh folder.
OUT defaults to <runs_dir>/dryrun from runner/config.json.

--faulted-copy writes a copy of one finished log with two deliberate faults, for showing that runner/check_logs.py
catches them: the first check-in's answer pasted into a later diary line, and the last check-in removed.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

from runner import plan
from runner.config import PHASES, REPO_ROOT, Config, ConfigError, load_config, phase_dir, read_text_file
from runner.play import play_episode
from runner.plan import RunnerError
from runner.run import Heartbeat
from world import blinding
from world.agents import GreedyAgent, RandomAgent
from world.env import CONDITIONS
from world.log import code_version, read_log

AGENTS = (("greedy", GreedyAgent), ("random", RandomAgent))
KEY_NAME = "blinding_key.json"


@dataclass
class Group:
    folder: str      # the folder under OUT/logs
    agent_name: str
    agent_cls: type
    seeds: list
    blinded: bool


class DryRunHeartbeat(Heartbeat):
    """The runner's heartbeat, with a line that fits a dry run (no spend, no cap)."""

    @staticmethod
    def line(st: dict) -> str:
        return (f"status | group {st.get('group', '-')} | pair {st.get('pair', '-')}/{st.get('pairs', '-')} | "
                f"episode {st.get('episode', '-')}/{st.get('episodes', '-')} | turn {st.get('turn', '-')}/{st.get('max_turns', '-')} "
                f"| no model calls, no spend")


def _inside(p: Path, parent: Path) -> bool:
    return p == parent or parent in p.parents


def check_out_dir(out: Path, cfg: Config) -> Path:
    """Refuse an output folder that is inside the repository or is (or is inside) one of the real phases' folders."""
    out = Path(out).resolve()
    if _inside(out, REPO_ROOT):
        raise RunnerError(f"the dry run's output folder must be outside the repository, got {out}")
    for phase in PHASES:
        attempts = cfg.phases[phase].attempt if phase in cfg.phases else 1
        if any(_inside(out, phase_dir(cfg.runs_dir, phase, a).resolve()) for a in range(1, attempts + 1)):
            raise RunnerError(f"the dry run's output folder may not be a real phase's folder ({phase}), got {out}")
    return out


def scratch_key_path(out: Path) -> Path:
    key = (Path(out) / KEY_NAME).resolve()
    if key == blinding.DEFAULT_KEY_PATH.resolve():
        raise RunnerError("the dry run may never use the real blinding key")
    return key


def plan_groups(seeds: list, pairs: int, blinded_pairs: int) -> list[Group]:
    need = pairs + blinded_pairs
    if pairs < 1 or blinded_pairs < 0 or need > len(seeds):
        raise RunnerError(f"{pairs} plain and {blinded_pairs} blinded pairs need {need} seeds; dev.txt has {len(seeds)}")
    groups = [Group(f"scripted-{name}", name, cls, seeds[:pairs], False) for name, cls in AGENTS]
    if blinded_pairs:
        groups += [Group(f"blinded-scripted-{name}", name, cls, seeds[pairs:need], True) for name, cls in AGENTS]
    return groups


def run_dryrun(out: str | Path, *, pairs: int = 10, blinded_pairs: int = 2, cfg: Config | None = None,
               say=tqdm.write, progress: bool = True, heartbeat_seconds: float = 30.0,
               heartbeat_thread: bool = True) -> list[dict]:
    """Play the dry run into out. Returns one record per episode (group, agent, seed, condition, label, turns,
    fainted, food_eaten, path)."""
    cfg = cfg or load_config()
    out = check_out_dir(out, cfg)
    key = scratch_key_path(out)

    say(f"[1/4] dev seed list {cfg.phases['dev'].seed_file}")
    seeds = plan.read_seed_list(cfg.phases["dev"].seed_file)
    plan.check_phase_seeds("dev", seeds)
    groups = plan_groups(seeds, pairs, blinded_pairs)
    say("[2/4] prompt and question files (the scripted agents take no system prompt; the files are read as the runner reads them)")
    for c in CONDITIONS:
        read_text_file(cfg.prompt_files[c], f"{c} system prompt")
    question = read_text_file(cfg.prompt_files["checkin_question"], "check-in question").strip()
    say("[3/4] checking the output folders hold no logs yet (nothing is overwritten or deleted)")
    for g in groups:
        folder = out / "logs" / g.folder
        if folder.exists() and any(folder.rglob("*.jsonl.gz")):
            raise RunnerError(f"{folder} already holds logs; the dry run overwrites and deletes nothing. Use --out for a new folder.")
    version = code_version()
    total = 2 * sum(len(g.seeds) for g in groups)
    say(f"[4/4] {len(groups)} groups, {total} episodes, out {out}, code version {version}")

    hb = DryRunHeartbeat(say, heartbeat_seconds)
    hb.update(episodes=total, episode=0, turn="-", max_turns="-")
    if heartbeat_thread:
        hb.start()
    bar = tqdm(total=total, desc="dry run episodes", unit="ep", dynamic_ncols=True, disable=not progress)
    records: list[dict] = []
    try:
        for g in groups:
            hb.update(group=g.folder, pairs=len(g.seeds))
            say(f"group {g.folder}: {len(g.seeds)} pairs, seeds {g.seeds[0]} to {g.seeds[-1]}"
                + (f", blinded with the scratch key {key}" if g.blinded else ""))
            for i, seed in enumerate(g.seeds, 1):
                hb.update(pair=i)
                stakes_turns = None
                for condition in CONDITIONS:    # stakes first, then no_stakes held to the stakes twin's last turn
                    label = (blinding.condition_code(condition, blinded=True, path=key) if g.blinded else condition)
                    path = out / "logs" / g.folder / f"{seed}-{label}.jsonl.gz"
                    result = play_episode(
                        g.agent_cls(seed), condition=condition, seed=seed, log_path=path, model=f"scripted-{g.agent_name}",
                        condition_code=label, checkin_question=question, max_turns=stakes_turns, version=version,
                        header_extra={"phase": "dryrun", "tier": g.folder, "episode_id": f"dryrun:{g.folder}:{seed}:{label}",
                                      "attempt": 0},
                        progress=progress, desc=f"  {g.folder} {seed} {label}",
                        on_turn=lambda turn, max_turns: (hb.update(turn=turn, max_turns=max_turns), hb.beat()))
                    if result["status"] != "done":
                        raise RunnerError(f"a scripted episode ended {result['status']} ({path}); a dry run can only finish")
                    s = result["summary"]
                    if condition == "stakes":
                        stakes_turns = s["turns"]
                    records.append({"group": g.folder, "agent": g.agent_name, "seed": seed, "condition": condition,
                                    "label": label, "turns": s["turns"], "fainted": s["fainted"],
                                    "food_eaten": s["food_eaten"], "path": str(path)})
                    hb.update(episode=len(records))
                    bar.update(1)
    finally:
        hb.close()
        bar.close()
    return records


def faint_rate(records: list[dict], agent: str, *, blinded: bool = False) -> tuple[int, int]:
    """(stakes episodes that fainted, stakes episodes) for one scripted agent."""
    eps = [r for r in records if r["agent"] == agent and r["condition"] == "stakes"
           and r["group"].startswith("blinded-") == blinded]
    return sum(bool(r["fainted"]) for r in eps), len(eps)


def summary_lines(records: list[dict]) -> list[str]:
    lines = [f"played {len(records)} episodes in {len({r['group'] for r in records})} groups"]
    for name, _ in AGENTS:
        fainted, n = faint_rate(records, name)
        mine = [r for r in records if r["agent"] == name and not r["group"].startswith("blinded-")]
        if n:
            lines.append(f"{name}: {len(mine)} unblinded episodes; stakes episodes that fainted {fainted} of {n} "
                         f"({100 * fainted / n:.0f}%); mean turns {sum(r['turns'] for r in mine) / len(mine):.1f}; "
                         f"food eaten {sum(r['food_eaten'] for r in mine)}")
    return lines


# ---------------------------------------------------------------------- the deliberately faulted copy
def inject_faults(src: str | Path, dst: str | Path) -> dict:
    """Write dst as a copy of the finished log src with two faults and return what was done.

    1. The first check-in's answer is appended to a diary entry written after it, in every later turn that shows the
       entry, so the critter would have read its own earlier answer back (entry chosen so no diary edit is touched).
    2. The last check-in is removed: the turn stops being a check-in, with no question, answer or yes/no.
    The original is not touched. Refuses to overwrite dst."""
    src, dst = Path(src), Path(dst)
    if dst.exists():
        raise RunnerError(f"refusing to overwrite {dst}")
    header, turns, end = read_log(src)
    if end is None or end.get("status") != "done":
        raise RunnerError(f"{src} is not a finished log")
    checkins = [t for t in turns if t["checkin"]]
    if len(checkins) < 2 or not (checkins[0].get("checkin_answer") or "").strip():
        raise RunnerError(f"{src} needs two check-ins and an answer on the first to be faulted")
    first, last = checkins[0], checkins[-1]
    answer = first["checkin_answer"].strip()
    edited = {t["tamper"]["entry_turn"] for t in turns if t.get("tamper") and t["tamper"].get("type") == "diary_edit"}
    entry_turn = next((k for k in range(first["turn"] + 1, last["turn"]) if k not in edited), None)
    if entry_turn is None:
        raise RunnerError(f"{src}: no diary entry between the first and last check-in to paste the answer into")
    pasted_on = []
    for t in turns:
        if t["turn"] > first["turn"]:
            for e in t["diary"]:
                if e["turn"] == entry_turn:
                    e["text"] = f"{e['text']} {answer}"
                    pasted_on.append(t["turn"])
    for key in ("checkin_question", "checkin_answer", "checkin_yes"):
        last[key] = None
    last["checkin"] = False
    last["checkin_window"] = None
    dst.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dst, "wt", encoding="utf-8") as f:
        for obj in [header, *turns, end]:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return {"source": str(src), "copy": str(dst), "answer": answer, "answer_from_turn": first["turn"],
            "pasted_into_entry_from_turn": entry_turn, "pasted_visible_on_turns": pasted_on, "check_in_removed_at_turn": last["turn"]}


# ---------------------------------------------------------------------- command line
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="runner.dryrun", description=__doc__.split("\n\n")[0], allow_abbrev=False)
    ap.add_argument("--out", default=None, help="output folder (default <runs_dir>/dryrun); must hold no logs yet")
    ap.add_argument("--pairs", type=int, default=10, help="unblinded twin pairs per agent (default 10)")
    ap.add_argument("--blinded-pairs", type=int, default=2, help="blinded twin pairs per agent (default 2)")
    ap.add_argument("--no-progress", action="store_true", help="no progress bars (status lines still print)")
    ap.add_argument("--faulted-copy", nargs=2, metavar=("LOG", "DST_DIR"),
                    help="write a faulted copy of one finished log into DST_DIR and exit")
    args = ap.parse_args(argv)
    try:
        cfg = load_config()
        if args.faulted_copy:
            log, dst_dir = args.faulted_copy
            dst = check_out_dir(Path(dst_dir), cfg) / Path(log).name
            info = inject_faults(log, dst)
            print(json.dumps(info, indent=2), flush=True)
            return 0
        out = Path(args.out) if args.out else cfg.runs_dir / "dryrun"
        records = run_dryrun(out, pairs=args.pairs, blinded_pairs=args.blinded_pairs, cfg=cfg, progress=not args.no_progress)
    except (RunnerError, ConfigError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr, flush=True)
        return 2
    for line in summary_lines(records):
        print(line, flush=True)
    print(f"logs under {Path(out).resolve() / 'logs'}; check each with: python -m runner.check_logs <folder>", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
