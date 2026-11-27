# 014 result: runner ready for the pilot and the Fable/Mythos tiers

**Done, no API call made, fake client only.** 152 tests pass (85 before, 67 new, about 51 s). I broke four of the new guards on purpose (expiry edge, the 2x factor, the 401 branch, the redo file) and each time a test failed; files restored.

**Files (all `runner/`):** changed `config.py`, `config.json`, `plan.py`, `run.py`, `claude_critter.py`, `play.py`, `fake_client.py`, `prices/2026-11-26.json`, tests `helpers.py`, `test_caps.py`, `test_gate.py`, `test_run.py`. New `seeds/{pilot,confirmatory,reserve,tiers}.txt` (40, 1300, 200, 150), `seeds/make_seeds.py`, `seeds/README.md` (generator seed 20261127, rebuild with `python runner/seeds/make_seeds.py --check`), `tests/test_{seeds,auth,key_expiry,heartbeat,tiers}.py`.

**What it does now**
- Tiers phase: fable `claude-fable-5-2`, mythos `claude-mythos-5-2` (one config value), cap $150, 30 pairs each, priors 1.30, prices added. Order strictly alternates fable, mythos. Both models play the same seed for each pair. Reserve cap is 0, list kept. Confirmatory cap 650; refusal above the preregistered caps stays (tiers ceiling 150). The confirmatory shuffle is unchanged (tested).
- 401 or authentication_error: run stops at once, no retry, not an exclusion, the log closes as `incomplete_auth`, and the exact line prints. The error text is never carried, so the key can't reach a line or log (tested). Exit code 5.
- Resume: finished episodes skip; the incomplete one is replayed on the same seed into a new `.r1` log with its own ledger id. The old log stays untouched.
- Heartbeat: a line every 30 s from a background thread, so a slow call can't hide it.
- `--key-expires`: required for every phase but dev. Prints hours left, stops before a pair if now + 2 x estimate + 1 h passes expiry, with your exact message. Exit code 5.

**Dry runs.** The real-config dev dry run exits 2: `prompts/checkin_question.txt` is missing (left alone as told). I ran dev and a tiers dry run through a scratch config with a dummy question. Tail of tiers (2 pairs): `finished: 2 pairs, 4 episodes run, 0 exclusions, spend $1.3251 of $150.00`, exit 0.

**Blocks the pilot**
1. `prompts/checkin_question.txt` does not exist, so every phase refuses to start.
2. Pilot `pairs_per_tier` is still 0/0/0; it needs your numbers.
3. The runner job line must now carry `--key-expires <time>`, renewed each week. I did not touch the watcher.

**Worth knowing**
- `--client fake` on a real phase with the real config writes fake spend into the real ledger and manifest, and a real run would then skip those pairs. Not changed. Use a scratch config.
- A 403 permission_error is not treated as a key failure (spec says 401 only); it would end as three exclusions, exit 4.
- `claude-mythos-5-1` has no price entry; add one if you switch.
- Scratch left on M:, not deleted: `Lobster-Lab\runs\_runner_test_tmp` (20 MB), `_runner_demo_014`.
