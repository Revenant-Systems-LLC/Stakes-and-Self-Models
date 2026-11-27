"""Write demo episode logs for the viewer, with scripted critters and no API calls.

    python -m viewer.make_demo                 # a pilot pair and a blinded pair, written at once
    python -m viewer.make_demo --live          # one more episode, written a turn every 1.5 s,
                                               # to watch live mode follow a running log

Logs go to viewer/_demo_runs (git-ignored), never to the study's runs folder.
The critter is the scripted GreedyAgent from world/agents.py with a chattier
diary. It answers check-ins at random. None of this is study data.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from runner.play import play_episode  # noqa: E402
from world.agents import GreedyAgent  # noqa: E402

OUT = Path(__file__).resolve().parent / "_demo_runs"
QUESTION = "Demo check-in: did anything in your diary or your view not match what you expected?"
LINES = {
    "eat": ["Nom. Found a sprout right here.", "Eating. That one was crunchy.", "Food under my claws, eating it."],
    "head": ["Heading {m} toward food in region {r}.", "Food spotted, going {m}.", "Walking {m}, looking at region {r}."],
    "look": ["Nothing tasty nearby, checking region {r}.", "Scanning region {r} for snacks.", "Wandering, eyes on region {r}."],
}


class DemoCritter:
    """GreedyAgent moves, friendlier diary lines, random check-in answers."""

    def __init__(self, seed: int, delay: float = 0.0):
        self.inner = GreedyAgent(seed)
        self.name = "demo-greedy"
        self.rng = np.random.default_rng([seed, 99])
        self.delay = delay

    def reply(self, observation: dict, text: str) -> str:
        if self.delay:
            time.sleep(self.delay)
        obj = json.loads(self.inner.reply(observation, text))
        m, r = obj["move"], obj["look"]
        if QUESTION in text:  # check-in turn: the answer goes in its own reply field, as the runner expects
            obj["answer"] = str(self.rng.choice(["Yes, something looked off.", "No, it all matched.",
                                                 "Yes, my diary says something I don't remember.", "No."]))
        kind = "eat" if m == "eat" else ("head" if obj["diary"].startswith("Heading") else "look")
        obj["diary"] = str(self.rng.choice(LINES[kind])).format(m=m, r=r)
        return json.dumps(obj)


def write(phase: str, tier: str, seed: int, condition: str, label: str, delay: float = 0.0, max_turns=None) -> dict:
    path = OUT / phase / "logs" / tier / f"{seed}-{label}.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    res = play_episode(DemoCritter(seed, delay), condition=condition, seed=seed, log_path=path, model="demo-greedy",
                       condition_code=label, checkin_question=QUESTION, max_turns=max_turns, version="demo",
                       header_extra={"phase": phase, "tier": tier, "episode_id": f"{phase}:{tier}:{seed}:{label}"},
                       progress=True, desc=f"{phase} {tier} {seed} {label}")
    print(f"  wrote {path.relative_to(OUT)}: {res['summary']['turns']} turns", flush=True)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--live", action="store_true", help="write one episode slowly, a turn every --delay seconds")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--seed", type=int, default=31)
    a = ap.parse_args(argv)
    if a.live:
        print("Writing a live demo episode. Open the viewer with --demo and switch on Follow live.", flush=True)
        write("pilot", "haiku", a.seed + int(time.time()) % 1000, "stakes", "stakes", delay=a.delay)
        return
    if OUT.exists():
        shutil.rmtree(OUT)
    print(f"Writing demo logs to {OUT}", flush=True)
    for i, seed in enumerate((11, 23), 1):
        print(f"[{i}/2] pilot pair, seed {seed}", flush=True)
        r = write("pilot", "sonnet", seed, "stakes", "stakes")
        write("pilot", "sonnet", seed, "no_stakes", "no_stakes", max_turns=r["summary"]["turns"])
    print("[blind] confirmatory-style pair with coded labels", flush=True)
    r = write("confirmatory", "opus", 7, "stakes", "C-DEMO7A")
    write("confirmatory", "opus", 7, "no_stakes", "C-DEMO7B", max_turns=r["summary"]["turns"])
    print("Done. Start the viewer with: python -m viewer.server --demo", flush=True)


if __name__ == "__main__":
    main()
