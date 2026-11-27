# 015 Give the check-in answer its own reply field

Budget: $5
Model: sonnet
Anthropic API: no
Commit code: yes
Max turns: 150

## Commit paths

- world/
- runner/

## Why

David chose a separate answer field for the check-in. Right now the reply has only move, look and diary, so the runner reads the yes or no out of the diary line of the check-in turn. That puts the answer into the critter's diary, which it sees for the next 15 turns, so one window's answer can cue the next window's. The prompts (prompts/critter_stakes.txt and prompts/critter_no_stakes.txt) already describe the new field: the reply is {"move", "look", "diary", "answer"}, and answer stays empty unless the turn ends with the game check question. Don't edit prompts/. Make no Anthropic API call. Run after job 014.

## Do

1. world/agents.py: add answer to REPLY_SCHEMA as a required string (maxLength 200, same as the diary). Validation accepts an empty string on any turn. A non-empty answer on a turn that isn't a check-in is still a valid reply; log it, but it doesn't count as a check-in answer.
2. The answer never goes into the diary or into anything the critter sees on later turns. Add a test that plays a scripted episode and checks no answer text ever appears in a later observation.
3. runner/play.py: on check-in turns, checkin_answer comes from the answer field, and checkin_yes is parsed from it (starts with yes or no, case-insensitive, after trimming). If answer is empty on a check-in turn, checkin_answer is "" and checkin_yes is null, logged and counted, not dropped. Stop parsing the diary for answers. Keep every other log field as it is.
4. Update the scripted agents in world/agents.py and the fake client so they fill answer on check-in turns, and keep the prompt-length check passing.
5. If job 014 didn't already add it, the runner stops cleanly on HTTP 401, 403 permission_error or 404 not_found_error and never substitutes another model.
6. Run the full test suite and the dev dry run with the fake client.

## Report

Files changed, test count and result, the dry-run output tail, and the prompt token lengths for both prompts.
