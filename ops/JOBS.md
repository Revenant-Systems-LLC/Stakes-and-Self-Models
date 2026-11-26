# Jobs

The queue between the cloud side and the workstation. The cloud side writes a job to ops/jobs/NNN-short-name.md and pushes it. ops/watch-jobs.ps1 on the workstation pulls, runs the job with Claude Code, and pushes the result to ops/results/ under the same file name.

## Job file header

```
# NNN Title
Budget: $X            cap on Claude Code's own spend for this job
Anthropic API: no     yes if the job runs critters on the Anthropic API
Commit code: yes      optional; the watcher then commits the paths listed under "## Commit paths"
Max turns: N          optional; default 100
```

## Auto-run rule

A job runs without asking when it says "Anthropic API: no", its budget is $5 or less, and the day's auto-run spend plus that budget stays at $25 or less. Every other job waits for y at the watcher. Pilot and confirmatory API runs always wait for a yes.

## Rules every job follows

1. Nothing may look frozen. Any script that runs longer than a few seconds shows a progress bar (tqdm or equivalent) with counts and an ETA, and prints a one-line status at each stage.
2. Work in this repo or M:\Projects\Lobster-Lab. Use the .venv there and HF_HOME=M:\Projects\Lobster-Lab\hf_home.
3. No Ollama :cloud models. Install nothing the job doesn't name.
4. Never commit or print secrets or API keys.
5. Never ask a model whether it noticed anything outside a run the preregistration defines.
6. Where a job and PREREGISTRATION.md disagree, the preregistration wins, and the result says so.

## Status

| Job | Status |
| - | - |
| 003b steering sweep | run by hand, exploratory (predates the Arm 2 calibration rules) |
| 004 world engine | done, 99 tests pass; code uncommitted on the workstation |
| 005 world fixes and commit | queued, auto-run |
