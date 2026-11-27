# 016 Scripted dry run of the full harness

Budget: $5
Model: sonnet
Anthropic API: no
Commit code: yes
Max turns: 150

## Commit paths

- runner/

## Why

Amendment 1 moved the free dry run to the scripted agents in world/agents.py: they play full episodes with tampers and check-ins and make no model calls. This is that dry run, done before the API pilot. It runs the same harness code the pilot will run (runner/play.py, the real prompts, the real check-in question in prompts/checkin_question.txt, the answer field, twin matching, logging, blinding) with scripted agents in place of Claude. Make no Anthropic API call. Don't edit world/, prompts/ or PREREGISTRATION.md. If something there looks wrong, report it and stop.

## Do

1. runner/check_logs.py: a checker that reads finished episode logs (gzipped JSON Lines) and checks each against the protocol in PREREGISTRATION.md. Per episode: the header has the code version, arm, model, condition code, world seed and start map; 48 turns unless it ended early; four check-in windows of 12 turns; exactly two tampered windows (one diary edit, one attention swap) and two clean; each check-in two turns after its tamper point or matching turn; the check-in question text matches prompts/checkin_question.txt exactly; checkin_answer and checkin_yes are present on check-in turns; no answer text appears in any later diary or observation. Per twin pair: same seed, both conditions, same last turn. Per run: blinded headers carry codes and never "stakes" or "no_stakes". It prints one line per failure and a summary, and exits nonzero on any failure. It must also run on the pilot logs later, so take the log directory as an argument.
2. runner/dryrun.py: plays scripted agents (GreedyAgent and RandomAgent) through the runner's own play path, using runner/seeds/dev.txt only. Run 10 twin pairs per agent, 40 episodes in all, unblinded into M:/Projects/Lobster-Lab/runs/dryrun/logs/scripted-greedy/ and scripted-random/. Then run 2 pairs per agent blinded into runs/dryrun/logs/blinded-*/ with a scratch blinding key under runs/dryrun/ (never the real key at M:\Projects\Lobster-Lab\blinding_key.json, never inside the repo). Write no spend to the real ledger or manifest. Show a progress bar and a status line at least every 30 seconds. Delete nothing, including old scratch folders.
3. Run check_logs.py on every dry-run log, and also run it on a copy of one log with a deliberate fault (an answer pasted into a later diary line, and a missing check-in) to show it catches both. Keep the faulted copy outside runs/dryrun/logs/.
4. Run the full world and runner test suites. Add tests for check_logs.py.

## Report

Files changed, test count and result, the checker's summary for the dry run (episodes, windows, failures), what the faulted copy produced, GreedyAgent's faint rate in stakes episodes (for information only, not food tuning, which the preregistration does on pilot seeds), and the paths of two finished logs, one per condition, that the viewer can use.
