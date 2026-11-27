# 015 result: the check-in answer has its own reply field

**Done, no API call, fake client only.** `world` + `runner`: **316 tests pass** (about 84 s). I broke two guards on purpose (answer leaked into the diary; answer read from the diary again) and tests failed each time; files restored.

**Files**
- `world/agents.py`: `answer` is a required string, maxLength 200 (the diary's constant). Empty is valid on any turn; a three-field reply is now invalid. Scripted agents answer on check-in turns (they spot "Game check:"); `RandomAgent` uses its own RNG stream so answers never change its moves.
- `runner/play.py`: `checkin_answer` and `checkin_yes` come from the answer field. The diary is never parsed. Empty or invalid reply on a check-in turn: `""` and null, counted as `empty_checkin_answers` in the end line. Non-empty answer off a check-in turn: valid, logged as new field `stray_answer`, counted as `stray_answers`, not a check-in answer. Other log fields unchanged.
- `runner/claude_critter.py`, `run.py`: 014 handled only 401, so I added 403 `permission_error` and 404 `not_found_error`. The run stops at once: no retry, no exclusion, no other model, log closed `stopped_access`, exit 5. The API's error text is never carried.
- `runner/fake_client.py`, `tests/helpers.py`: fake replies carry `answer`.
- Tests: new `test_answer_field.py` (marker test: no answer text appears in any later observation or logged diary); `test_world.py`, `test_critter.py`, `test_run.py` updated.

**Dry runs.** The real config exits 2: `prompts/checkin_question.txt` still doesn't exist (same as 014, not created). Through a scratch config with the preregistered wording: dev tail `finished: 6 pairs, 12 episodes run, 0 exclusions, spend $0.5244 of $10.00`; tiers, 2 pairs: `finished: 2 pairs, 4 episodes run, 0 exclusions, spend $1.3261 of $150.00`. Both exit 0. In the 16 logs: 12 check-ins, 8 yes, 4 no, 0 empty, 0 stray.

**Prompt tokens** (Qwen2.5 tokenizer, offline; no Claude tokenizer here): stakes 522, no_stakes 515, gap 1.3% (limit 10%). Prompts untouched.

**Needs you**
1. `arm2/tests` (outside this job's paths, not edited): 3 tests now fail because their scripted replies have three fields (`test_bad_first_reply_is_retried_with_a_new_seed`, `test_full_episode_through_run_episode`, `test_window_patch_through_a_real_episode`). `test_windows_and_key_order` already failed at HEAD because the prompt lists `answer`. arm2 is the retired arm.
2. yes/no parsing keeps the existing rule, which tolerates leading punctuation (`"No"` counts). Say if you want it stricter.
3. **Boundary slip:** I wrote two scratch copies to `C:\Users\Dave\AppData\Local\Temp` (`env.py.bak`, `play.py.bak`), outside the write zone. Not deleted, since C: deletes need your approval.
4. Scratch left on M:: `Lobster-Lab\runs\_015_scratch`.
