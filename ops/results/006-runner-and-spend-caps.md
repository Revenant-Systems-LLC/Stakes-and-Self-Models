# 006 result: runner with hard spending caps

**Built and tested, no API call made.** 85 pytest tests pass (`runner/tests`, about 29 s). Deliberately breaking the cap check, the pre-episode rule and the gate made the tests fail; files restored. The watcher will commit `runner/`.

**anthropic:** installed in the Lobster-Lab venv, version 2.14.0. It is imported only inside `gate.make_claude_client()` and the preflight; every other module and every test runs without it. `output_config` is in its `messages.create` signature; the request shape is otherwise unchecked, since nothing was sent.

**Files (all `runner/`):** `config.json`, `config.py`, `ledger.py`, `gate.py`, `fake_client.py`, `claude_critter.py`, `play.py`, `plan.py`, `run.py`, `prices/2026-11-26.json`, `seeds/dev.txt`, `tests/` (conftest, helpers, test_ledger, test_caps, test_gate, test_critter, test_run). Run: `python -m runner.run --phase dev --client fake` (dry run showed status lines and progress bars).

**Preregistration vs the job file:** no conflict found.

**Ambiguities and how I resolved them (all flagged for you):**
- **Check-in answer channel (the big one).** `REPLY_SCHEMA` allows only move, look and diary, and I may not edit `world/`. So the answer is the diary text of the check-in turn; `checkin_yes` is parsed from it (starts with yes or no). Recommend a world change (an optional answer key) before the pilot. `world/episode.run_episode` also can't carry the question, tokens or cost, so `play.py` is a parallel loop (a test shows it matches `run_episode` otherwise).
- "Running mean" is per tier, per phase, over finished (`done`) episodes only. "Crossed the cap" means spend strictly above it.
- Config caps above the preregistered 100, 750 and 150 are refused. Dev runs use the fake client only. Three exclusions in a row stop the run (my guard).
- Confirmatory logs, ledger lines and file names use the blinded codes, not condition names.

**Left before a pilot can run:**
1. `prompts/checkin_question.txt` (the runner refuses without it; I wrote no question text).
2. Seed lists `runner/seeds/pilot.txt`, `confirmatory.txt`, `reserve.txt`, fixed by you.
3. `pairs_per_tier` for pilot and reserve is 0 in the config; confirmatory is 400/400/250 as planned.
4. Your decision on the answer channel.
5. An API job you approve, with the key set by the watcher.

**Disclosure.** During a mutation check I ran `cp runner/ledger.py /tmp/ledger.bak`, which landed on the system drive: `C:\Users\Dave\AppData\Local\Temp\ledger.bak` (9,878 bytes). That is outside the write zone. I did not delete it; a C: delete needs your approval. Scratch left on M:, not deleted: `Lobster-Lab\runs\_runner_test_tmp` (2.2 MB), `_mut`, `_runner_demo`.
