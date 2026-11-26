# 010 Commit arm2/

Budget: $0.50
Model: haiku
Anthropic API: no
Commit code: yes
Max turns: 20

## Commit paths

- arm2/

## Goal

Jobs 007 and 009 left arm2/ on this machine uncommitted, because the watcher that ran them didn't allow arm2/ commits. The current watcher does. This job only gets arm2/ committed. No GPU, no model loads, no runs.

## Steps

1. Run `git status --short arm2/` and list what is new or changed.
2. Check that arm2/ holds no keys, tokens, .env files, model weights, logs or run output. If any of that is there, stop and say what it is, and commit nothing.
3. Check that arm2/'s default behavior still matches 007 (the 009 variants are opt-in). Read only; don't run anything heavy. A quick `python -c "import arm2"` style import check with the repo .venv is fine.
4. Leave the files as they are. The watcher commits arm2/ with this result.

## Rules

- Don't edit anything outside your result file.
- Install nothing, download nothing, no Anthropic API, no Ollama.

## Result

One line saying what got staged for commit (file count and names), then anything from step 2 or 3 that looked off.
