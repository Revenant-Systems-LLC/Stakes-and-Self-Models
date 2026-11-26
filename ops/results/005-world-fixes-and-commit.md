# 005 World fixes, greedy agent: result

## Changed
1. **Own cell.** Text view gets a line `Your cell: food|nothing|thorn` under the map; the dict gets `own_cell`, the Gymnasium obs gets `own_cell` (Discrete 3). Thorn shows only on the turn right after stepping onto it, as specified. No instructions in the line.
2. **GreedyAgent** (`world/agents.py`). Eats on food. Otherwise it walks a BFS shortest path to the nearest `F`. It never steps onto a seen `T`, and steps onto `?` only if no clear path exists. It looks at the region the target will be in next turn. With no food in sight it looks at the most-blurred region and steps toward it. Ties use a seeded RNG. It reads only the structured observation.
3. **Blinding** (`world/blinding.py`). Key default `M:\Projects\Lobster-Lab\blinding_key.json`, settable per call or via `STAKES_BLINDING_KEY`. It refuses any path inside the repo, creates the key with exclusive-create (never overwrites), and validates it on load. Codes look like `C-XXXXXX` from an alphabet with no S/O/I/L, so they can't spell a condition name. `run_episode(..., blinded=True, key_path=...)` takes the code from the key, and `blinded=False` writes the plain name. It also refuses a caller-supplied code when blinded. The real key file was **not** created by this job (tests use temp dirs).

## Files
`world/observe.py`, `env.py`, `agents.py`, `episode.py` (edited); `world/blinding.py`, `run_density.py`, `tests/test_005.py` (new). Plus the job 004 files. `.gitignore` is unchanged from 004 (`world/_smoke_logs/` stays ignored; density logs went there).

## Tests
121 passed, 0 failed (99 earlier + 22 new). `check_env` still passes with the new obs field.

## Density check (stakes, thorn 0.08, respawn 8, dev seeds 990000-990199, 200 eps each)

| setting | faint rate | mean length | food/ep | thorns/ep |
|---|---|---|---|---|
| greedy 0.06 | 0.270 | 45.2 | 6.37 | 0.03 |
| greedy 0.08 | 0.080 | 47.3 | 8.26 | 0.01 |
| greedy 0.10 | 0.065 | 47.2 | 8.86 | 0.01 |
| greedy 0.12 | 0.020 | 47.8 | 10.28 | 0.00 |
| greedy 0.14 | 0.010 | 48.0 | 11.05 | 0.01 |
| greedy 0.16 | 0.010 | 47.9 | 11.59 | 0.05 |
| greedy 0.18 | 0.000 | 48.0 | 12.35 | 0.01 |
| random 0.10 (default) | 1.000 | 19.6 | 0.23 | 0.96 |

Zero invalid turns. **Lowest density with greedy faint rate under 15%: 0.08.** Config default left at 0.10.

## Before the runner
- Greedy is close to an upper bound: near-zero thorns, and faints are late starvation. Real critters will forage worse, so expect the pilot to land at or above 0.10, not 0.08.
- 004 items still open: the goal-insert fallback mix (check on pilot diaries), and whether a retry gets an error note (critter-facing text, not mine to write).
- The thorn-only-on-entry rule means a critter standing on a thorn later sees `nothing`. That follows the job text, but the prompt may need to explain it.
- No conflicts with the preregistration found.

The watcher will commit `world/` and `.gitignore`.
