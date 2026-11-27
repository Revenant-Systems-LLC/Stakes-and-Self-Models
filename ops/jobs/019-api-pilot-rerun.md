# 019 API pilot rerun (attempt 2)

Anthropic API: yes
Runner: -m runner.run --phase pilot --client claude --key-expires 2026-12-03T21:35-06:00

## Why

Pilot attempt 1 (job 018) is void. The reply validator threw out usable replies and turned them into stay turns with blank diary lines, which starved stakes critters and left blanks that look like tampering. The fix and the rerun rule are preregistration amendment 3. David in the chat on Nov 27: "Fix it. You don't need my fucking yes. Fix it."

Same split as 018: 5, 3, 2, 1 and 1 twin pairs on Haiku, Sonnet, Opus, Fable and Mythos. runner/config.json now sets the pilot to attempt 2, so this writes to M:\Projects\Lobster-Lab\runs\pilot-attempt2 and only reads runs\pilot. Every seed attempt 1 touched is skipped for every tier. The pilot ledger is shared, so attempt 1's spend counts against the same $100 cap.

Stop 018 first if it is still running, so two pilot processes never share the ledger. Do not type 018 again; with the new config it would run as this rerun anyway.

--key-expires is key A's expiry (about 9:35 PM Chicago on Dec 3). With a new key, change it.

The watcher runs this only after David types the job number.
