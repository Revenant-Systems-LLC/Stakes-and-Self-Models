# 008a Find out why job 006 has no result

Budget: $0.50
Model: haiku
Anthropic API: no
Max turns: 20

## Goal

Job 006 (runner and spend caps) has no result in ops/results, but 007 and 008 ran after it. Find out why from the files on this machine. Change nothing.

## Rules

1. Print a one-line status before each step.
2. Read only. Don't delete, rename, create or edit anything except your result file. Don't run any job. Install nothing.
3. Never print anything that looks like an API key or token. If a log line contains one, write "[key redacted]" instead.

## Look at

- ops/logs/: list every file with its size and last-write time.
- Whether ops/logs/006-runner-and-spend-caps.skipped, or any ops/logs/006*.skipped, exists.
- Whether ops/results/006-runner-and-spend-caps.md exists in the working tree. If it does, whether git tracks it, whether it's in a commit that was never pushed (git log origin/main..HEAD), and its first 30 lines.
- Every ops/logs/spend-*.txt file, in full (they hold only time, job, mode and cost).
- ops/logs/006-runner-and-spend-caps.log, if it exists: its size, first 20 lines and last 40 lines, keys redacted.
- Whether runner/ exists in the repo working tree, and if so its files and git status.
- git status, git log origin/main..HEAD --oneline, and the last 10 lines of git log --oneline.

## Result

Lead with the most likely reason 006 didn't finish: skipped on purpose, waiting at the watcher's y/n prompt because it fell outside the auto-run rule, interrupted part way (Ctrl+C or a restart), failed, or never seen. Then the evidence for it, and the sum of today's auto-run spend from the spend file.
