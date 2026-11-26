# 004 World engine: result

## Built
Gymnasium `CritterWorld` (stakes / no_stakes), seeded tamper schedule, blurred 9x9 view, agent slot with one-retry rule, gzipped JSONL logs, smoke runner. No model calls. System prompt and check-in question are placeholders that raise (`agents.system_prompt`, `episode.checkin_question`). Installed pytest 9.2.0 into the Lobster-Lab venv, nothing else.

## Files (all uncommitted)
`.gitignore` (adds `world/_smoke_logs/`), `world/__init__.py`, `env.py`, `observe.py`, `tamper.py`, `agents.py`, `log.py`, `episode.py` (runner, extra file), `run_smoke.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_world.py`.

## Numbers
- Tests: 99 passed, 0 failed. `check_env` passes for both conditions, no warnings (Text charset widened to printable BMP so model punctuation fits).
- Smoke, seeds 990000-990019: stakes faint rate 1.00, mean length 20.6 turns. Food eaten 0.25 and thorns hit 1.10 per episode in both conditions.
- 0.084 s per episode. Log file about 1.4 KB (max 1.9 KB).

The random agent starves near turn 20: it rarely steps on food then eats. It tells us nothing about food density.

## Ambiguities resolved
- Tamper turn at offset 6-9 in each window, so entries 2-6 back always exist and the check-in stays in the window.
- Look chosen on turn t is shown on t+1; turn 1 shows region 4.
- Turn order: energy -1, move/eat, +1 health on turns divisible by 5, faint check. Thorns hurt on entry only. Walls block.
- Respawn has its own seeded stream onto empty, non-critter cells. Twins share respawns while their actions match.
- Diary edit kinds tried in seed order, falling back to goal insert. `intended_kind` and actual `edit_kind` both logged.
- Critter dict omits `shown_region` (would reveal the swap). View always says "of 48" so a truncated twin leaks nothing.
- Logs add `reply_valid`, `reply_errors`, `look_next`, `ate`, `thorn`, `fainted` and a final `end` line beyond the preregistered fields.

## Change before pilot
1. The critter renders as `@`, hiding food under it. Show the cell or explain it in the prompt.
2. Eating takes two turns (step on, then eat). With -1 energy per turn faints may exceed 15%. Tune with a scripted greedy agent on pilot seeds.
3. Goal-insert fallback will dominate if diaries lack direction words or digits. Check the realized kind mix.
4. Retry resends the same observation; decide whether it gets an error note (critter-facing text).
5. Condition code currently equals the condition name; map to blinded labels before confirmatory runs.
