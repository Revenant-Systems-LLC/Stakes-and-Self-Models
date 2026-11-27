# 026 Pilot attempt 4: summary and faint causes

Budget: $1
Model: haiku
Anthropic API: no
Commit code: no
Max turns: 20

## Why

Job 025 is the second food density tuning round, at 0.20 (preregistration amendment 4). The cloud side needs each tier's faint rate, its causes, cost per episode and the log checker's verdict to apply the amendment's decision rule.

This job is read-only. Write nothing except the results file. Delete, move, rename or overwrite nothing. Install nothing, make no network call, and run no git command that changes anything. Do not count yes answers, hits or false alarms, and do not quote check-in answers.

## Do

If M:\Projects\Lobster-Lab\runs\pilot-attempt4 does not exist, say so and stop. Otherwise, first `Set-Location M:\Projects\Stakes-and-Self-Models` (the study repo, which holds the runner package). Then run these three commands there with the study's venv Python, one at a time. Each takes seconds.

1. `M:\Projects\Lobster-Lab\.venv\Scripts\python.exe -m runner.summarize_run M:\Projects\Lobster-Lab\runs\pilot-attempt4`
2. `M:\Projects\Lobster-Lab\.venv\Scripts\python.exe -m runner.faint_report M:\Projects\Lobster-Lab\runs\pilot-attempt4`
3. `M:\Projects\Lobster-Lab\.venv\Scripts\python.exe -m runner.check_logs M:\Projects\Lobster-Lab\runs\pilot-attempt4\logs`

If a command fails, put its full error in the results and go on to the next.

## Report

Paste the full output of all three commands, each in its own code block, with the exit code under it. Do not summarize or reword the output.
