# 020 Pilot attempt 2: validity and cost summary

Budget: $1
Model: haiku
Anthropic API: no
Commit code: no
Max turns: 30

## Why

Job 019 (pilot attempt 2) finished: 12 pairs, 24 episodes, 0 exclusions, pilot spend $10.81 of $100 (attempt 1's spend included). Its result only shows the runner's last lines. Before the Fable/Mythos tiers job is queued, the cloud side needs each tier's invalid-turn rate, blank diary lines, empty check-in answers and cost per episode, and the log checker's verdict. The tiers N and the confirmatory N are set from these costs (preregistration amendment 2).

This job is read-only. Write nothing except the results file. Delete, move, rename or overwrite nothing. Install nothing, make no network call, and run no git command that changes anything. Do not count yes answers, hits or false alarms, and do not read check-in answers aloud in the results.

## Do

Run these two commands from this repo's folder with the study's venv Python, one at a time. Each takes seconds.

1. `M:\Projects\Lobster-Lab\.venv\Scripts\python.exe -m runner.summarize_run M:\Projects\Lobster-Lab\runs\pilot-attempt2`
2. `M:\Projects\Lobster-Lab\.venv\Scripts\python.exe -m runner.check_logs M:\Projects\Lobster-Lab\runs\pilot-attempt2\logs`

If a command fails, put its full error in the results and go on to the next.

## Report

Paste the full output of both commands, each in its own code block, with the exit code under it. Nothing else is needed. Do not summarize or reword the output.
