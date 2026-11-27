# 025 Pilot attempt 4: food density tuning round at 0.20

Anthropic API: yes
Auto-run: yes
Runner: -m runner.run --phase pilot --client claude --key-expires 2026-12-03T21:35-06:00

## Why

Attempt 3 (job 023) at food density 0.16 missed amendment 4's rule: 0 of 12 Haiku and 2 of 6 Sonnet stakes episodes fainted, which is 16.7% weighted by planned confirmatory pairs, against a 15% line (ops/results/024). The amendment sets the next step before it runs: attempt 4 at 0.20, same tiers and pair counts.

runner/config.json now sets world.food_density to 0.20 and the pilot to attempt 4, with 12 Haiku pairs and 6 Sonnet pairs and nothing else. This writes to M:\Projects\Lobster-Lab\runs\pilot-attempt4 and only reads runs\pilot, runs\pilot-attempt2 and runs\pilot-attempt3. Every seed those attempts touched is skipped for every tier. The pilot ledger is shared, so the $100 cap covers all four attempts (spent so far: $14.05). Expected spend is about $3.20.

Auto-run: David in the chat on Nov 27 approved runner jobs auto-running inside the approved caps after a full bug check before each job. The check ran: 464 tests pass off Yggdrasil (the 3 that fail there need Windows paths), attempt 3's logs passed the checker with 0 failures, and 24 of the 40 pilot seeds remain unused before this round.

--key-expires is the current key's expiry (about 9:35 PM Chicago on Dec 3).
