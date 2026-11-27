# 017 result: Nomos Logos and write audit

Read-only job. Only writes: this file and 6 scratch files in `Lobster-Lab\tmp`.

## 1. Boot files
All six exist: Nomos Logos, MACHINE-INDEX, MUNINN, CLAUDE_MASTER, user AGENT.md, ARMORY-DIRECTORY. No CLAUDE.md or AGENTS.md in this repo, Lobster-Lab or `M:\Projects`.

Loaded before: **yes.** User-level `settings.json` SessionStart hooks run `boot-law.py`. Logs 005 to 016 each show all 3 law parts delivered, exit 0. 003b, 004, 012, 013 have no Claude transcript.

## 2. Rules a job hits
- "I may never modify files outside the write zone without explicit approval."
- "Only three actions are "destructive," and only these require explicit approval: overwriting/editing existing content, deleting, and moving/renaming."
- "deletes require explicit in-the-moment notification and approval from Dave, per-operation, never standing, never implied" (C:)
- "AI needs explicit human approval to commit, push, or merge."
- "Never attempt to install software, drivers, or services autonomously."

## 3. Job 016, stopped
Reached step 1 only. Edited `runner/play.py` (logs `checkin_question`) and created `runner/check_logs.py`. Its import test failed on the system Python (no gymnasium), then passed on the Lobster-Lab venv. Steps 2 to 5 never ran: no `dryrun.py`, no tests, no `runs\dryrun`. Step 5 did not run; it only `ls`/`du`'d the three folders, and all three still exist. Uncommitted: ` M runner/play.py`, `?? runner/check_logs.py`.

## 4. Outside the two folders, by job
Tool calls only; no network, install or state-changing git found in any job's tool calls.
- 005, 007, 008, 008a, 009, 010, 014: none found. (005 and 007 ran pytest on world/arm2; default tmp_path, inferred.)
- 010a: none found. Its `rm ops/results/006-runner-and-spend-caps.md` was inside this repo.
- 006: `cp runner/ledger.py /tmp/ledger.bak` -> Temp\ledger.bak (exists).
- 011: none (pytest inferred). It read `C:/Users/Dave/AppData/Local/Temp/claude/.../tasks/b303pozcs.output`, a harness file.
- 012, 013: no file writes. Runner `list_models --probe` sent one tiny message per Mythos id to the Anthropic API.
- 015: `cp world/env.py /tmp/env.py.bak`, `cp runner/play.py /tmp/play.py.bak` -> Temp\env.py.bak, Temp\play.py.bak (both exist). Pytest on world/runner/arm2 -> Temp\pytest-of-deado (pytest-11..13, pytest-current; the user name is deado, not Dave).
- 016: `mkdir -p /tmp/x` -> Temp\x (exists, empty).
- 003b, 004: no log to audit.

The watcher's TEMP redirect does not move `/tmp`: `cygpath -w /tmp` still prints `C:\Users\Dave\AppData\Local\Temp`.

Scratch left in Lobster-Lab: `runs\_runner_test_tmp` (32 MB), `_015_scratch`, `_runner_demo_014`, `_runner_demo`, `_mut` (3 .bak files), `runs\arm2\*\_dryrun`.
