# 023 Pilot attempt 3: food density tuning round

Anthropic API: yes
Auto-run: yes
Runner: -m runner.run --phase pilot --client claude --key-expires 2026-12-03T21:35-06:00

## Why

Pilot attempt 2 (job 019) is valid, but 4 of 12 stakes critters fainted, all from running out of energy (ops/results/022). The preregistration tunes food density on pilot seeds so fewer than 15% of stakes episodes faint, and that step never ran. Preregistration amendment 4 sets the round and its decision rule before it runs.

runner/config.json now sets world.food_density to 0.16 and the pilot to attempt 3, with 12 Haiku pairs and 6 Sonnet pairs and nothing else. This writes to M:\Projects\Lobster-Lab\runs\pilot-attempt3 and only reads runs\pilot and runs\pilot-attempt2. Every seed those attempts touched is skipped for every tier. The pilot ledger is shared, so the $100 cap covers all three attempts (spent so far: $10.81). Expected spend is about $4.

Auto-run: David in the chat on Nov 27 approved runner jobs auto-running inside the approved caps after a full bug check before each job. The check ran: 464 tests pass off Yggdrasil (the 3 that fail there need Windows paths), and every episode now records its food density.

--key-expires is the current key's expiry (about 9:35 PM Chicago on Dec 3).
