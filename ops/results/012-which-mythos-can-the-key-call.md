# Result for 012-which-mythos-can-the-key-call (runner job)

Ran: python -m runner.list_models --probe
Took: 0m05s

Last lines of output (key-like strings redacted):

```
[1/3] Listing models...
  15 ids listed
  Fable and Mythos ids listed: claude-fable-5, claude-fable-5-1, claude-fable-5-2
[2/3] Checking each study model...
  claude-haiku-5-5: HTTP 200, listed=True, effort low supported=True
  claude-sonnet-5-5: HTTP 200, listed=True, effort low supported=True
  claude-opus-5-5: HTTP 200, listed=True, effort low supported=True
  claude-fable-5-2: HTTP 200, listed=True, effort low supported=True
  claude-mythos-5-2: HTTP 404, not_found_error: model: claude-mythos-5-2
  claude-mythos-5-1: HTTP 404, not_found_error: model: claude-mythos-5-1
[3/3] One tiny message to each Mythos id...
  claude-mythos-5-2: NOT CALLABLE, HTTP 404, not_found_error: model: claude-mythos-5-2
  claude-mythos-5-1: NOT CALLABLE, HTTP 404, not_found_error: model: claude-mythos-5-1
Done.
watcher: runner exit code 0
```
