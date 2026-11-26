# 005 World fixes, greedy agent, commit the world

Budget: $4
Anthropic API: no
Commit code: yes

## Commit paths

- world/
- .gitignore

## Goal

Job 004 built world/ and left it uncommitted. This job fixes the pre-pilot items from ops/results/004-world-engine.md, adds a scripted greedy agent for a first food-density check, and then the watcher commits world/ and .gitignore so the cloud side can review the code.

Read PREREGISTRATION.md ("The world", "The two conditions", "Episode logs") and ops/results/004-world-engine.md first. Where this file and the preregistration disagree, the preregistration wins; note it in your result.

## Rules

1. Nothing may look frozen. Any script that runs longer than a few seconds shows a tqdm progress bar with counts and an ETA, and prints a one-line status at each stage. Print a line before each pytest run and each sweep.
2. Use M:\Projects\Lobster-Lab\.venv. tqdm may be installed into it if missing; install nothing else.
3. No Anthropic API calls, no Ollama, no model loading.
4. Write no critter system prompts and no check-in question text.
5. Don't edit PREREGISTRATION.md, README.md or anything under ops/ except your result file. Don't commit or push; the watcher does.
6. Keep world/_smoke_logs/ and any other generated logs out of world/ paths that get committed (they are gitignored; keep it that way).
7. No secrets or keys anywhere in world/.

## What to change

1. Own cell. The critter is drawn as @ and hides what's under it. Add a plain fact line to the text rendering and a field in the structured observation saying what is on the critter's own cell (food, or nothing; a thorn only on the turn it stepped on one). No instructions to the critter in that line.
2. Greedy agent. Add world/agents.py GreedyAgent: a scripted forager that returns valid JSON, eats when on food, otherwise walks toward the nearest food it can see in full detail, avoids thorns it can see, and looks at the region with the most blur symbols when it sees no food. Seeded where it needs ties broken.
3. Blinded condition codes. Add world/blinding.py. A key file outside the repo (default M:\Projects\Lobster-Lab\blinding_key.json, path settable) maps stakes and no_stakes to two random codes, created once if missing and never overwritten. Logs take condition_code from it when blinded=True and use the plain name when blinded=False (pilots). The key path must not be under the repo. Add a test that the codes differ, stay fixed across calls, and that blinded logs never contain the words stakes or no_stakes in the header's condition code.
4. Tests for each change, added to world/tests/. All earlier tests must still pass.

## Density check (dev seeds only)

Seeds 990000 to 990199 are development seeds and never go into a pilot or confirmatory run. With GreedyAgent in the stakes condition, sweep food density over 0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18 at thorn density 0.08 and respawn 8, 200 episodes per setting. Report per setting: faint rate, mean episode length, food eaten and thorns hit per episode. Also report the same table for RandomAgent at the current default. Don't change the config default; name the lowest density where the greedy faint rate is under 15%. This is a starting point for the pilot only, because the preregistration says density is tuned on pilot seeds with real critters.

## Result

Write the result file the watcher names, under 400 words: what changed, the file list, the test count, the density table, and anything you'd change before the runner gets built. Say that the watcher will commit world/ and .gitignore.
