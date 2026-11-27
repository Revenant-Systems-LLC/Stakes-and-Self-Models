# Jobs

The queue between the cloud side and the workstation. The cloud side writes a job to ops/jobs/NNN-short-name.md and pushes it. ops/watch-jobs.ps1 on the workstation pulls, runs the job with Claude Code, and pushes the result to ops/results/ under the same file name.

## Job file header

```
# NNN Title
Budget: $X            cap on Claude Code's own spend for this job
Anthropic API: no     yes if the job runs critters on the Anthropic API
Commit code: yes      optional; the watcher then commits the paths listed under "## Commit paths"
Model: sonnet         optional; default sonnet. haiku, sonnet or opus
Max turns: N          optional; default 100
```

## Runner jobs (critters on the Anthropic API)

```
# NNN Title
Anthropic API: yes
Runner: -m runner.run --config runner/configs/pilot.toml
```

A job with a Runner line doesn't go to Claude Code. The watcher shows the command and waits for David to type the job number. It then starts the study's venv Python with those arguments in its own background process. Only inside that process does it decrypt the key from the DPAPI vault (default A:\env\Clawlings.dpapi, set with -VaultPath), set ANTHROPIC_API_KEY and STAKES_ALLOW_API=yes, and clear both when the process ends. The key is never printed, logged, written or given to Claude Code, and any output line that looks like a key is redacted. Spend is capped by the runner's own ledger and phase caps. No runner job is queued without David's yes in his own words in the chat.

## Model choice

Jobs run headless, so nobody talks to the model directly. Pick the cheapest one that can do the job:

- haiku: simple jobs such as commits, file moves, running existing scripts, summarizing logs.
- sonnet: normal code work. This is the default.
- opus: only when the job genuinely needs it, such as hard design or debugging that sonnet already failed at. Say why in the job file.

## Auto-run rule

A job runs without asking when it says "Anthropic API: no", its budget is $5 or less, and the day's auto-run spend plus that budget stays at $25 or less. Every other job waits for y at the watcher. Pilot and confirmatory API runs always wait for a yes.

## Rules every job follows

1. Nothing may look frozen. Any script that runs longer than a few seconds shows a progress bar (tqdm or equivalent) with counts and an ETA, and prints a one-line status at each stage.
2. Work in this repo or M:\Projects\Lobster-Lab. Use the .venv there and HF_HOME=M:\Projects\Lobster-Lab\hf_home.
3. No Ollama :cloud models. Install nothing the job doesn't name.
4. Never commit or print secrets or API keys. API keys never go in user or system environment variables. Only the watcher passes one, decrypted from DPAPI, to the single process of a job that is approved to use it.
5. Never ask a model whether it noticed anything outside a run the preregistration defines.
6. Where a job and PREREGISTRATION.md disagree, the preregistration wins, and the result says so.

## Status

| Job | Status |
| - | - |
| 003b steering sweep | run by hand, exploratory (predates the Arm 2 calibration rules) |
| 004 world engine | done, committed with 005 |
| 005 world fixes and commit | done, 121 tests pass, world/ committed; greedy faints under 15% from food density 0.08 |
| 006 runner and spend caps | never ran; a stale local fallback stub made the watcher think it was done (008a). 010a clears it so 006 reruns |
| 007 local Qwen critter | done; runs and hook checks out, but the critter walks south and starves; arm2/ not committed (watcher path bug, fixed) |
| 008 check model access | stopped, no key in its process; rerun once the watcher can hand the key to one job from DPAPI |
| 008a why 006 didn't run | done: untracked fallback stub in ops/results/ on Yggdrasil |
| 009 commit arm2/, forage diagnosis | done; no prompt variant made it forage (it picks the move before reading the map, then copies its diary); arm2/ still not committed |
| 010 commit arm2/ | done, arm2/ committed (842151b) |
| 010a clear stale 006 stub | done, stub deleted |
| 011 reason-first replies, shorter diary | done: nothing forages; the move ignores the food in every variant; no change recommended |
| 012 can the model read the map | dropped with the local arms (preregistration amendment 1, Nov 26) |
| 012 which Mythos can the key call | done: both Mythos ids 404 (no access on the Clawlings workspace); Fable 5.2 and the 5.5 tiers callable |
| 013 Mythos check after CVP | done: claude-mythos-5-2 and claude-mythos-5-1 callable |
| 014 runner ready for pilot and tiers | done: seed lists, tiers phase, 401 stop, resume, heartbeat, expiry guard; 152 tests |
| 015 check-in answer field | done: answer field, kept out of the diary, 403/404 stop added; 316 tests |
| 016 scripted dry run | held in ops/held/ until the watcher loads Nomos Logos for every job |
| 017 find Nomos Logos, audit writes | queued, auto-runs (no API, $3, read-only): where the harness lives and how to load it; every out-of-bounds write so far |
