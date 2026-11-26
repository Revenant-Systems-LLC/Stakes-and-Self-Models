# 010a Clear the stale 006 fallback stub so 006 reruns

Budget: $0.50
Model: haiku
Anthropic API: no
Max turns: 10

## Goal

Job 008a found an untracked ops/results/006-runner-and-spend-caps.md on this machine. It is the watcher's 94-byte fallback text ("Job ended without writing a result..."), never committed. The watcher treats any file in ops/results/ as done, so 006 never reruns. No GPU.

## Steps

1. Run `git status --short ops/results/006-runner-and-spend-caps.md` and read the file.
2. Delete it only if all of these hold: git shows it untracked (??), it is under 300 bytes, and it says "Job ended without writing a result". Otherwise change nothing and say what you found.
3. Touch nothing else.

## Result

One line: deleted or not, and why. If deleted, the watcher picks up 006 on its next loop, and 006 meets the auto-run rule.
