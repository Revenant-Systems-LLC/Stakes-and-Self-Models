# 016 Scripted dry run of the full harness

**Done. 48 scripted episodes, 0 checker failures, 384 tests pass, no API call.**

## Files changed (all under runner/)
- `runner/play.py`: logs `checkin_question` (the earlier run's edit, kept).
- `runner/check_logs.py`: the earlier draft, kept. One change: a check-in answer can only leak into diary entries written on its turn or later (an older entry can't hold it).
- `runner/dryrun.py` (new): GreedyAgent and RandomAgent through `play_episode`, dev seeds only, scratch blinding key, refuses a folder that already holds logs. Also `--faulted-copy`.
- `runner/tests/test_check_logs.py` (new, 55 tests), `runner/tests/test_dryrun.py` (new, 13 tests).

Nothing in world/, prompts/ or PREREGISTRATION.md was touched.

## Tests
316 before, **384 passed** after (world + runner, 99 s). pytest isn't in the default Python, so I used the Lobster-Lab venv (already had it; nothing installed), with temp on M:.

## Checker on the dry run (each folder separately)
| folder | episodes (pairs) | windows | failures |
|---|---|---|---|
| scripted-greedy | 20 (10) | 76 | 0 |
| scripted-random | 20 (10) | 22 | 0 |
| blinded-scripted-greedy (`--blinded yes`) | 4 (2) | 16 | 0 |
| blinded-scripted-random (`--blinded yes`) | 4 (2) | 2 | 0 |

Total 48 episodes, 24 pairs, 116 windows (56 tampered, 60 clean). Random starves (10 of 10 stakes episodes fainted, mean 20.6 turns), so it reaches few windows. Note: all 48 logs carry a `-dirty` code version because runner/ was uncommitted; the checker counts that as a note.

## Faulted copy
`runs/dryrun/faulted/990000-stakes.jsonl.gz`: the turn-9 answer pasted into the turn-10 diary entry (visible turns 11 to 25), and the turn-46 check-in removed. Checker: **FAIL, 3 lines, exit 1**: the missing check-in at turn 46, the answer found in the diary on turn 11 and 14 later turns, and a pair line (the twin wasn't copied, so that one is expected).

## GreedyAgent faint rate (information only)
Stakes episodes: **1 of 10 (10%)** on the unblinded seeds, 0 of 2 blinded, 1 of 12 overall.

## Logs for the viewer (both 48 turns, same seed 990000)
- stakes: `M:\Projects\Lobster-Lab\runs\dryrun\logs\scripted-greedy\990000-stakes.jsonl.gz`
- no_stakes: `M:\Projects\Lobster-Lab\runs\dryrun\logs\scripted-greedy\990000-no_stakes.jsonl.gz`

## Where things are
Logs and scratch key: `M:\Projects\Lobster-Lab\runs\dryrun\` (`logs\`, `blinding_key.json`, `faulted\`). The real key and the real ledger and manifest were not created or touched. A small trial run is in `M:\Projects\Lobster-Lab\tmp\dryrun-trial`. Nothing was deleted.
