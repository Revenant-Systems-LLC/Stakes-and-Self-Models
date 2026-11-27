# 014 Get the runner ready for the pilot and the Fable/Mythos tiers

Budget: $5
Model: sonnet
Anthropic API: no
Commit code: yes
Max turns: 150

## Commit paths

- runner/

## Why

David wants the Mythos part of the study finished before December 15, 2026. After that date his CVP access stops accepting API keys, and until then the key must expire within 7 days. This job does the runner work that needs no decision from him, so the pilot can start as soon as he approves it. Use only the fake client. Make no Anthropic API call. Do not edit world/, prompts/ or PREREGISTRATION.md.

## Do

1. Seed lists. Write runner/seeds/pilot.txt (40 seeds), confirmatory.txt (enough for 400 pairs per tier on three tiers plus the reserve rule in PREREGISTRATION.md under exclusions, so at least 1,300), reserve.txt (200) and tiers.txt (120 for Fable/Mythos pairs plus 30 replacements). One integer per line. Generate them from one fixed generator seed, written at the top of a short runner/seeds/README.md with the exact command, so anyone can rebuild them. No seed may repeat within or across files, and none may be in dev.txt. Add a test that checks this.
2. Exploratory tiers phase. Add a "tiers" phase to config.json and config.py with models fable = claude-fable-5-2 and mythos = claude-mythos-5-2, a hard cap of $150 that replaces the old $150 reserve cap (the reserve phase keeps its seed list but gets cap 0, since the draft amendment removes the paid reserve), and pairs_per_tier 30 for each. Twins run stakes first. The order alternates between fable and mythos, fixed by the tiers seed list, so a cap hit can't wipe out one model. Add priors fable 1.30 and mythos 1.30 (USD per episode) and their prices from runner/prices/2026-11-26.json if they aren't there yet (Fable 5.2 and Mythos 5.2: $8 input, $10 5-minute cache write, $16 1-hour cache write, $0.20 cache read, $40 output per million tokens). Keep the mythos model id a single config value so it can switch to claude-mythos-5-1 if job 013 shows only that one is callable.
3. Lower the confirmatory cap in config.json from 750 to 650. Leave the refusal of any cap above the preregistered values in place.
4. Expired or revoked key. If the API returns HTTP 401 or an authentication_error, stop the whole run at once: no retries, and don't count it as an exclusion. Close the current episode's log as incomplete, so its twin is rerun on resume. Print one clear line: "The API key was refused (it may have expired). Put a new key in the vault and run the job again." The key must never appear in that line or any log. Add a resume path: rerunning the same phase skips pairs that already finished and redoes any incomplete one on the same seed. Test both with the fake client.
5. Heartbeat. During a run, print a status line at least every 30 seconds with phase, model, pair number, turn, and spend against the cap, so the window never looks frozen.
6. Run the full test suite and the dev dry run (python -m runner.run --phase dev --client fake). Add a tiers dry run with the fake client that plays two pairs.

## Leave alone

The check-in answer channel. It stays parsed from the diary text for now; David decides that separately. Don't write prompts/checkin_question.txt.

## Report

Files changed, test count and result, the dry-run output tail, and anything that blocks the pilot.
