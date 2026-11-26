# 008a: why 006 has no result

**Most likely: 006 failed or stopped before its Claude Code run got going, and the watcher wrote the generic fallback.** Confidence 45%. The only trace left is that fallback stub, and the log it points to does not exist.

Ruled out:
- **Skipped on purpose:** no `ops/logs/006*.skipped` file.
- **Waiting at the y/n prompt:** 006 meets the auto-run rule (`Anthropic API: no`, budget $5, day total $0 + $5 is under $25). 005 ran in auto mode at the same time. Low weight (10%), since the rule text may not match the version that ran.

Evidence:
- **No 006 files in `ops/logs/`:** no `.log`, no `.prompt.md`. `Invoke-Job` writes both before Claude Code starts, and only a rerun deletes the log. 006 never reran, so something else removed them or the run never reached `Invoke-Job`.
- **`ops/results/006-runner-and-spend-caps.md`** (untracked, 94 bytes, 20:38 local): "Job ended without writing a result. See ops/logs/006-runner-and-spend-caps.log on Yggdrasil." That is the watcher's fallback text. It was never committed.
- **No 006 line in `spend-2026-11-25.txt`:** `Add-Spend` runs in a `finally` after every run, so its absence fits "never reached Claude Code". It does not fit the fallback path, which only runs after `Add-Spend`. I could not resolve that from the files.
- **Timing:** 006 was committed at 02:37:21 UTC (2423636). The stub at 20:38 local matches 02:38 UTC if local time is UTC-6. That is inferred, not checked. So the run came within about a minute of the job being added, on an earlier watcher version.
- **The job file has changed since:** `Model:` was added in e6486ca and the API-key preflight in 1e3c676. The 006 file on disk is not the version that ran.

Rough split for the cause: failed 45%, interrupted (Ctrl+C or a watcher restart) 25%, never seen or other 20%, waiting at y/n 10%.

Settling it needs what is not on disk: the console output of the `watch-jobs.ps1` window around 20:38 local on 2026-11-25.

**Auto-run spend today** (`spend-2026-11-25.txt`, all auto):
- 005 world-fixes: $1.0011
- 007 local-qwen-critter: $1.9217
- 008 check-model-access: $0.0092
- 009 arm2-commit: $3.3916
- **Total: $6.3236** (006 has no line, so it adds nothing)

Nothing was changed. No jobs were run. Open for Dave: whether to delete the stale 006 stub, and whether to rerun 006 (that needs his y).
