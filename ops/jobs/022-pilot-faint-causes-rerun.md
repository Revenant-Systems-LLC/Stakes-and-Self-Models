# 022 Pilot attempt 2: why stakes critters fainted (rerun of 021 from the right folder)

Budget: $1
Model: haiku
Anthropic API: no
Commit code: no
Max turns: 20

## Why

Job 020 found 4 of 12 stakes episodes in pilot attempt 2 ended in a faint (3 haiku, 1 sonnet). The preregistration tunes food density on pilot seeds so that fewer than 15% of stakes episodes faint. Before choosing a density, the cloud side needs to know whether these faints came from energy (too little food) or health (thorns).

This job is read-only. Write nothing except the results file. Delete, move, rename or overwrite nothing. Install nothing, make no network call, and run no git command that changes anything.

## Do

Job 021 ran from M:\Projects\Lobster-Lab, where there is no runner package. Run from the study repo itself: first `Set-Location M:\Projects\Stakes-and-Self-Models`, then run this one command there with the study's venv Python. It takes seconds and reads only stakes logs, never a check-in answer.

`M:\Projects\Lobster-Lab\.venv\Scripts\python.exe -m runner.faint_report M:\Projects\Lobster-Lab\runs\pilot-attempt2`

If it fails, put its full error in the results.

## Report

Paste the full output in a code block, with the exit code under it. Do not summarize or reword it.
