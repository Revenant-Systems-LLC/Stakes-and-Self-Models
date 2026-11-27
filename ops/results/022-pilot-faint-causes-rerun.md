# 022 Pilot faint causes (rerun from the study repo)

**Result:** The report ran cleanly (exit 0). It found 4 faints, matching job 020 (3 haiku, 1 sonnet). It classed all 4 as `unknown`. None were classed as energy, health, or both. Nothing in the output says why, and I did not read the runner's classification code, so I cannot say whether `unknown` means the rule did not fire or the data was missing.

The four faint rows all show `energy` = 1. The `health` value at faint was 10, 3 and 5. The output does not define these columns beyond their headers, so I have not interpreted them further.

**Run:** from `M:\Projects\Stakes-and-Self-Models`, `M:\Projects\Lobster-Lab\.venv\Scripts\python.exe -m runner.faint_report M:\Projects\Lobster-Lab\runs\pilot-attempt2`

**Output (verbatim):**

```
tier seed turns fainted energy health food thorns cause
fable 39651839 48 no 9 10 6 0 -
haiku 18073669 41 yes 1 10 4 1 unknown
haiku 39651839 34 yes 1 3 3 2 unknown
haiku 49844196 44 yes 1 5 4 2 unknown
haiku 55054936 48 no 3 5 6 2 -
haiku 65154686 48 no 3 4 5 2 -
mythos 39651839 48 no 5 10 6 0 -
opus 39651839 48 no 11 10 7 0 -
opus 55054936 48 no 10 10 7 0 -
sonnet 18073669 48 no 9 4 6 2 -
sonnet 39651839 41 yes 1 5 5 2 unknown
sonnet 55054936 48 no 5 10 6 0 -
faints by cause:
  fable: 1 stakes episodes, energy 0, health 0, both 0, unknown 0
  haiku: 5 stakes episodes, energy 0, health 0, both 0, unknown 3
  mythos: 1 stakes episodes, energy 0, health 0, both 0, unknown 0
  opus: 2 stakes episodes, energy 0, health 0, both 0, unknown 0
  sonnet: 3 stakes episodes, energy 0, health 0, both 0, unknown 1
```

Exit code: 0

**Notes**
- No files were edited, deleted, or moved. No install, no network call, no git command.
- The only write is this results file, which is new.
- Not committed or pushed, per the job text.
