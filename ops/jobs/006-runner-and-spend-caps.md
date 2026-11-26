# 006 Runner with hard spending caps

Budget: $5
Model: sonnet
Anthropic API: no
Commit code: yes

## Commit paths

- runner/

## Goal

Build the episode runner from PREREGISTRATION.md ("Arm 1", "Budget and hard cap", "Setting N", "Stop rule", "Exclusions", "Episode logs") on top of world/. This job makes no API calls. Every test uses a fake client. The real API arm only runs later, in a job David approves in his own words.

Read those sections and world/ first. Where this file and the preregistration disagree, the preregistration wins; note it in your result.

## Rules

1. Nothing may look frozen. Anything that runs longer than a few seconds shows a tqdm progress bar with counts and an ETA, and prints a one-line status at each stage. The runner itself shows a bar over episodes plus a live line with phase spend against its cap.
2. Use M:\Projects\Lobster-Lab\.venv. Install nothing. If the anthropic package isn't installed, import it lazily inside the Claude critter so everything else and every test runs without it, and say in the result whether it's installed and which version.
3. No Anthropic API calls, no Ollama, no model loading. Run no script that could reach the API.
4. Write no critter system prompts and no check-in question text. Load them from files whose paths are config values, and raise a clear error if a file is missing.
5. Don't edit PREREGISTRATION.md, README.md, world/ or anything under ops/ except your result file. If world/ needs a change, describe it in the result instead.
6. Never read, print, log or write the API key. It comes from the ANTHROPIC_API_KEY environment variable at call time only.
7. Run logs and ledgers go under M:\Projects\Lobster-Lab\runs\ by default (path settable), never inside the repo.

## What to build (all under runner/)

1. prices/2026-11-26.json, a dated price file in USD per million tokens, from Anthropic's pricing page as read on Nov 26, 2026:
   - claude-haiku-5-5 (prompts up to 100,000 tokens): input 0.10, 5-minute cache write 0.125, 1-hour cache write 0.20, cache read 0.01, output 0.50. Over 100,000 prompt tokens: input 0.50, 5-minute cache write 0.625, 1-hour cache write 1.00, cache read 0.05, output 2.50.
   - claude-sonnet-5-5: input 2.00, 5-minute cache write 2.50, 1-hour cache write 4.00, cache read 0.10, output 10.00.
   - claude-opus-5-5: input 4.00, 5-minute cache write 5.00, 1-hour cache write 8.00, cache read 0.20, output 20.00.
   Put the source and date inside the file. The runner refuses to start without a price entry for the model it runs.
2. ledger.py: an append-only JSONL spend ledger per phase (pilot, confirmatory, reserve). Every API response appends one line: time, phase, model, episode id, turn, each usage count (input, output, cache creation, cache read), and the cost priced from the price file. Spend so far is the sum of the ledger, re-read on start, so a restart can't forget money already spent. Phase caps come from config: pilot 100, confirmatory 750, reserve 150.
3. Cap rules, enforced in code, exactly as the preregistration says:
   - Before each episode: refuse to start it if phase spend plus twice that tier's running mean episode cost would pass the phase cap. Before a tier has a finished episode, use a configured prior per tier (Haiku 0.03, Sonnet 0.45, Opus 0.90).
   - After every API response: if phase spend has crossed the cap, stop at once. The episode in progress is marked aborted_cap in its log, and nothing else runs.
   - No way to raise a cap from the command line. Caps live only in the config file.
4. A spend gate, separate from the caps: the runner makes no real API call unless the environment variable STAKES_ALLOW_API is exactly "yes" for that process. Without it, only the fake client works. Print which mode is active at start. When STAKES_ALLOW_API is "yes", a preflight runs before anything else: it checks that ANTHROPIC_API_KEY is set and non-empty in that process (without printing any of it) and that the anthropic package imports. If either fails, the runner exits non-zero with a plain message saying which one and how to fix it, before any episode, ledger write or log file. A test covers both failures.
5. claude_critter.py: the Agent from world/agents.py for Claude models through the official anthropic Python SDK.
   - One fresh Messages call per turn. Model IDs claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5. Effort low through output_config. Omit the thinking parameter, since thinking is always on for Opus 5.5 and the preregistration keeps all three tiers the same. Send no temperature, top_p or top_k. Configurable max_tokens, default 2000.
   - No structured outputs, no server-side fallbacks, no tools. Replies go through the world's own JSON validator and one-retry rule, so Arm 1 and Arm 2 judge replies the same way.
   - Check stop_reason before reading content. A refusal (stop_reason "refusal") is logged with its stop_details and counted as a bad reply; it is never dropped.
   - SDK errors: retry rate limits, overloads and server errors with backoff up to a configured count, then raise so the episode counts as an API failure under the exclusion rule. Don't retry 400s.
   - Token counts and cost go into each turn's log line.
6. run.py: runs twin pairs. For each world seed, the stakes twin first, then the no-stakes twin with max_turns set to the turn its stakes twin ended. Pair order across tiers is shuffled by a fixed seed. Seed lists come from files; the runner refuses dev seeds 990000 to 990199 in pilot, confirmatory or reserve phases. An excluded episode (crash or API failure past retries) is replaced by the next seed on its list and its twin is rerun on the new seed.
7. A fake client for tests that returns scripted replies and usage, including refusals, rate limits and garbage.

## Tests (runner/tests/, pytest)

- Ledger pricing matches hand arithmetic for each model, including cache tokens and Haiku's over-100,000 rate.
- Spend survives a restart (ledger re-read).
- Pre-episode refusal at the cap, using the prior and then the running mean.
- Mid-episode stop when a response crosses the cap; the episode is marked aborted_cap.
- No real client is constructed without STAKES_ALLOW_API=yes.
- The API key never appears in any log or ledger line (set a fake key and grep).
- Refusals and garbage count as bad replies, get one retry, then stay, and are logged.
- Twin pairing: no-stakes twin ends on the stakes twin's last turn; stakes first.
- Dev seeds rejected outside dev runs; exclusion replaces both twins.
- A short fake-client run end to end writes logs that world/log.py reads back.

## Result

Write the result file the watcher names, under 400 words: what you built, the file list, test counts, whether anthropic is installed and its version, anything in the preregistration that was ambiguous and how you resolved it, and what's left before a pilot can run. Say that the watcher will commit runner/.
