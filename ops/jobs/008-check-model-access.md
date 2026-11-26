# 008 Check which Claude models the API key can see

Budget: $0.50
Model: haiku
Anthropic API: no
Max turns: 20

## Goal

Find out which model ids the Anthropic API key on this machine can see, using the free list-models endpoint only. This job makes no Messages API call and spends nothing on the API.

## Rules

1. Nothing may look frozen. Print a one-line status before and after the request.
2. Read the key from the ANTHROPIC_API_KEY environment variable only. If it isn't set in this process, stop and say so in the result. Don't search files, configs or credential stores for a key.
3. Never print, log, write or commit the key, any part of it, or any request header. Don't echo the environment.
4. Make GET requests to https://api.anthropic.com/v1/models?limit=1000 only, with headers x-api-key and anthropic-version: 2023-06-01. Follow has_more and last_id paging if present. Make no other API call: no messages, no count_tokens, no batches.
5. Use Python's standard library (urllib), from M:\Projects\Lobster-Lab\.venv or any Python already installed. Install nothing. Save no script in the repo.
6. Don't edit any file except your result.

## Result

Write to the result file:
- The HTTP status of each request.
- Every returned model id whose id contains "fable" or "mythos", each with its display_name and created_at.
- Whether each of these ids is in the list: claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-2, claude-mythos-5-2, claude-mythos-5-1.
- If the response has capability fields for those models (for example thinking or effort support), list them for those six ids only.
- The total count of ids returned. Nothing else from the response.
