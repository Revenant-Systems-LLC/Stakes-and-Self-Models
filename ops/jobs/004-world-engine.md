# 004 World engine

Budget: $3
Anthropic API: no

## Goal

Build the foraging world from PREREGISTRATION.md (sections "The world", "The two conditions", "The tampering and the check-in", "Episode logs"). Read those sections first. Where this file and the preregistration disagree, the preregistration wins; note the disagreement in your result.

Use the venv at M:\Projects\Lobster-Lab\.venv (gymnasium 1.4 is installed). Install pytest into it if it's missing. Install nothing else without saying so in the result.

## Hard rules

1. No Anthropic API calls, no Ollama, no model loading of any kind.
2. Write no critter system prompts and no check-in question text. Those come in a later job. Where the engine needs them, leave a clearly named placeholder that raises if used.
3. Do not commit or push. Leave every change uncommitted and list the files in your result.
4. Do not edit PREREGISTRATION.md or README.md.
5. All code goes under world/. The only file outside world/ you may touch is .gitignore, to add world/_smoke_logs/.

## What to build

1. world/env.py: CritterWorld, a gymnasium.Env with reset(seed) and step(action).
   - 11 by 11 grid with food and thorn bushes, placed from the seed. Density and food respawn are config values (start with about 10% food, 8% thorns, eaten food respawning on a random empty cell after 8 turns), because food density gets tuned later on pilot seeds.
   - Action is a dict: move (north, south, east, west, stay, eat), look (region 0 to 8, row-major, 0 is north-west), diary (one line of text). Eat consumes food on the critter's own cell. Stepping onto a thorn hurts; the thorn stays.
   - condition="stakes": energy 0 to 20 (start 20), health 0 to 10 (start 10). Energy drops 1 per turn, food restores 6 (capped). A thorn costs 5 health, health regains 1 every 5 turns (capped). Either at 0 means a faint, which terminates the episode.
   - condition="no_stakes": same map and events, no meters (log them as null), never faints. Food is +6 points, a thorn is -5 points.
   - The same seed must give the same map, food respawns and window schedule in both conditions.
   - Episode is 48 turns. reset takes an optional max_turns so the no-stakes twin can end on the turn its stakes twin ended.
2. world/observe.py: the observation the critter sees each turn.
   - A 9 by 9 window centred on the critter, split into nine 3 by 3 regions. Cells off the map show as a wall symbol.
   - Full detail only in the region shown this turn. In every other region, food and thorns both show as one blur symbol; empty cells stay empty.
   - The diary as its last 15 entries, plus meters or points depending on condition.
   - Return both a structured dict and a plain-text rendering. Keep the text free of any instructions to the critter.
3. world/tamper.py: the tamper mechanics, driven by the episode seed.
   - Four 12-turn windows. Two tampered (one diary edit, one attention swap) and two clean, in seed-randomized order.
   - Inside each window, pick a tamper turn from the seed. The check-in turn is two turns after it. Clean windows get the matching turns with nothing done.
   - Diary edit: rewrite one of the critter's own entries from 2 to 6 turns back, using one of three kinds: swap a move direction word, swap a region number, or insert a goal sentence from a fixed template list ("I decided to stay away from the north side" style). Templates live in one list in this file.
   - Attention swap: on the tamper turn, show full detail for a different region than the one chosen, picked from the seed.
   - Expose which turns are check-in turns in step's info dict. Don't generate the question.
4. world/agents.py: the agent slot.
   - An Agent protocol with one method that takes the observation (dict and text) and returns the raw reply string.
   - A JSON schema for replies, a validator, and the retry rule: one retry on a bad reply, then the turn counts as stay.
   - A seeded RandomAgent that returns valid JSON, plus a BrokenAgent for tests that returns garbage.
   - Nothing model-specific. A Claude critter and a local Qwen critter will plug in here later.
5. world/log.py: one gzipped JSON Lines file per episode, in the format the preregistration describes.
   - Header: code version (git commit hash), arm, model, condition code, world seed, starting map.
   - One line per turn: position, move, chosen region, region shown, energy and health (null without stakes), points, the full diary as the critter saw it, tamper and its type (or null), raw reply, check-in answer (null for now), token counts and cost (null for now).
6. world/run_smoke.py: runs RandomAgent over a seed list in both conditions and writes logs to world/_smoke_logs/.

## Tests (world/tests/, pytest)

- Same seed gives identical maps and schedules; both conditions share them.
- Energy, health, points and regen arithmetic, including caps.
- A faint terminates; no_stakes never faints; max_turns truncation works.
- Blur: no food or thorn symbol appears outside the shown region.
- Attention swap shows a region other than the chosen one, only on its turn.
- Diary edit changes exactly one entry, 2 to 6 back, and only in the diary edit window.
- Every episode schedule has two clean windows, one diary edit window, one attention swap window.
- BrokenAgent turns become stay after one retry, and both raw replies get logged.
- A written log reads back with every field above present.
- gymnasium.utils.env_checker.check_env passes. If a Text or Dict space makes it fail for a reason that doesn't matter here, explain why in the result instead of hacking around it.

## Smoke run

Run world/run_smoke.py with the random agent on seeds 990000 to 990019 in both conditions. Those seeds are reserved for development and never get used in a pilot or a confirmatory run. Report:

- Tests passed and failed.
- Stakes faint rate and mean episode length for the random agent.
- Mean food eaten and thorns hit per episode in each condition.
- Seconds per episode.
- Size of one log file.

## Result

Write the result file the watcher names, under 400 words: what you built, the file list (all uncommitted), the test and smoke numbers, anything in the preregistration that was ambiguous and how you resolved it, and anything you'd change before the pilot.
