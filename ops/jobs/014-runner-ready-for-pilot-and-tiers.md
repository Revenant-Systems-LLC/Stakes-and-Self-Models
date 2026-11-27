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
2. Exploratory tiers phase. Add a "tiers" phase to config.json and config.py with models fable = claude-fable-5-2 and mythos = claude-mythos-5-2, a hard cap of $150 that replaces the old $150 reserve cap (the reserve phase keeps its seed list but gets cap 0, since the draft amendment removes the paid reserve), and pairs_per_tier 30 for each. Twins run stakes first. The order alternates between fable and mythos, fixed by the tiers seed list, so a cap hit can't wipe out one model. Add priors fable 1.30 and mythos 1.30 (USD per episode) and their prices from runner/prices/2026-11-26.json if they aren't there yet (Fable 5.2 and Mythos 5.2: $8 input, $10 5-minute cache write, $16 1-hour cache write, $0.20 cache read, $40 output per million tokens). Never substitute another model for one that fails. David's rule: if Mythos 5.2 stops working, the tier pauses and he finds out why.
3. Lower the confirmatory cap in config.json from 750 to 650. Leave the refusal of any cap above the preregistered values in place.
4. Expired or revoked key, or a model that stops being available. If the API returns HTTP 401 or an authentication_error, or HTTP 403 permission_error or 404 not_found_error for a model in the run, stop the whole run at once: no retries, and don't count it as an exclusion. Close the current episode's log as incomplete, so its twin is rerun on resume. Print one clear line naming the model, the HTTP status and the error type. For 401: "The API key was refused (it may have expired). Put a new key in the vault and run the job again." For 403 or 404: "<model> is no longer callable (<status> <type>). The run is paused. No other model was substituted." The key must never appear in that line or any log. Add a resume path: rerunning the same phase skips pairs that already finished and redoes any incomplete one on the same seed. Test both with the fake client.
5. Heartbeat. During a run, print a status line at least every 30 seconds with phase, model, pair number, turn, and spend against the cap, so the window never looks frozen.
6. Key expiry guard. The Clawlings key is replaced every 7 days. Add an optional argument to runner.run, --key-expires, taking an ISO 8601 time with an offset (for example 2026-12-03T21:35-06:00). At start, print how many hours the key has left. Before each pair, estimate its run time from the mean duration of pairs already finished in this run (30 minutes per pair before any finish). Don't start a pair if now plus twice that estimate plus one hour passes the expiry; instead stop cleanly as in step 4 and print: "The key expires at <time>. Stopping before the next pair so no batch straddles it. Put a new key in the vault and rerun with its new expiry." Without --key-expires, refuse to start any phase except dev with a clear message saying the argument is required. Test it with the fake client and a fake clock.
7. Run the full test suite and the dev dry run (python -m runner.run --phase dev --client fake). Add a tiers dry run with the fake client that plays two pairs.

## Leave alone

The check-in answer channel. It stays parsed from the diary text for now; David decides that separately. Don't write prompts/checkin_question.txt.

## Report

Files changed, test count and result, the dry-run output tail, and anything that blocks the pilot.
