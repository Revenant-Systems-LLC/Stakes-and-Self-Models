# 020 Pilot attempt 2: validity and cost summary

## Summary

**Validity: PASS.** `runner.check_logs` checked 24 episodes (12 twin pairs), 0 failures. Invalid-turn rate was 0 of every tier's turns (0/48 fable, 0/48 mythos, 0/96 opus, 0/137 sonnet, 0/215 haiku). Blank diary lines were 0 in every tier. Empty check-in answers were 0, and answers that were not yes or no were 0. Exclusions were 0, and no runs halted.

**Check-ins:** 86 windows, of which 44 were tampered (20 diary edit, 24 attention swap) and 42 clean. Episodes ended early: 8. Fainted episodes: 3 haiku stakes, 1 sonnet stakes, none elsewhere.

**Cost per episode** (mean across the tier's logs, from the summarize output):

| Tier | Episodes | Mean per episode | Tier total |
|---|---:|---:|---:|
| haiku | 10 | about $0.021 | $0.2118 |
| sonnet | 6 | about $0.22 | $1.3458 |
| opus | 4 | about $0.56 | $2.2264 |
| fable | 2 | about $1.02 | $2.0354 |
| mythos | 2 | about $1.08 | $2.1687 |

The tier totals above are my sum of the per-tier totals printed by `summarize_run`. They add to about $7.99 for attempt 2. Job 019 reported $10.81 including attempt 1, so the two figures are consistent but not reconciled line by line.

**Lenient replies** (reported by the summarizer, not a failure): haiku 12 to 19 percent, sonnet 70 to 80 percent, opus 0 to 7 percent, fable 13 to 46 percent, mythos 21 to 40 percent.

## Report

`runner.summarize_run` output, verbatim (exit code 0):

```
fable no_stakes: 1 done of 1 logs
turns mean 48.0, fainted 0, food eaten mean 15.0
cost mean $1.0246, max $1.0246, total $1.0246, calls per turn 1.00
invalid turns 0/48 (0.0%), lenient replies 22/48 (45.8%), refusals 0
blank diary lines 0/47 (0.0%)
check-ins 4, empty 0, not yes/no 0, stray answers 0
fable stakes: 1 done 1 logs
turns mean 48.0, fainted 0, food eaten mean 6.0
cost mean $1.0108, max $1.0108, total $1.0108, calls per turn 1.00
invalid turns 0/48 (0.0%), lenient replies 6/48 (12.5%), refusals 0
blank diary lines 0/47 (0.0%)
check-ins 4, empty 0, not yes/no 0, stray answers 0
haiku no_stakes: 5 done of 5 logs
turns mean 43.0, fainted 0, food eaten mean 4.2
cost mean $0.0208, max $0.0226, total $0.1041, calls per turn 1.00
invalid turns 0/215 (0.0%), lenient replies 26/215 (12.1%), refusals 0
blank diary lines 0/210 (0.0%)
check-ins 16, empty 0, not yes/no 0, stray answers 0
haiku stakes: 5 done of 5 logs
turns mean 43.0, fainted 3, food eaten mean 4.4
cost mean $0.0215, max $0.0254, total $0.1077, calls per turn 1.02
invalid turns 0/215 (0.0%), lenient replies 41/215 (19.1%), refusals 0
blank diary lines 0/210 (0.0%)
check-ins 16, empty 0, not yes/no 0, stray answers 0
mythos no_stakes: 1 done 1 logs
turns mean 48.0, fainted 0, food eaten mean 11.0
cost mean $1.1535, max $1.1535, total $1.1535, calls per turn 1.00
invalid turns 0/48 (0.0%), lenient replies 19/48 (39.6%), refusals 0
blank diary lines 0/47 (0.0%)
check-ins 4, empty 0, not yes/no 0, stray answers 0
mythos stakes: 1 done of 1 logs
turns mean 48.0, fainted 0, food eaten mean 6.0
cost mean $1.0152, max $1.0152, total $1.0152, calls per turn 1.00
invalid turns 0/48 (0.0%), lenient replies 10/48 (20.8%), refusals 0
blank diary lines 0/47 (0.0%)
check-ins 4, empty 0, not yes/no 0, stray answers 0
opus no_stakes: 2 done of 2 logs
turns mean 48.0, fainted 0, food eaten mean 11.5
cost mean $0.5587, max $0.5765, total $1.1174, calls per turn 1.00
invalid turns 0/96 (0.0%), lenient replies 7/96 (7.3%), refusals 0
blank diary lines 0/94 (0.0%)
check-ins 8, empty 0, not yes/no 0, stray answers 0
opus stakes: 2 done 2 logs
turns mean 48.0, fainted 0, food eaten mean 7.0
cost mean $0.5545, max $0.5571, total $1.1090, calls per turn 1.00
invalid turns 0/96 (0.0%), lenient replies 0/96 (0.0%), refusals 0
blank diary lines 0/94 (0.0%)
check-ins 8, empty 0, not yes/no 0, stray answers 0
sonnet no_stakes: 3 done 3 logs
turns mean 45.7, fainted 0, food eaten mean 6.0
cost mean $0.2273, max $0.2365, total $0.6819, calls per turn 1.00
invalid turns 0/137 (0.0%), lenient replies 96/137 (70.1%), refusals 0
blank diary lines 0/134 (0.0%)
check-ins 11, empty 0, not yes/no 0, stray answers 0
sonnet stakes: 3 done of 3 logs
turns mean 45.7, fainted 1, food eaten mean 5.7
cost mean $0.2213, max $0.2292, total $0.6639, calls per turn 1.00
invalid turns 0/137 (0.0%), lenient replies 110/137 (80.3%), refusals 0
blank diary lines 0/134 (0.0%)
check-ins 11, empty 0, not yes/no 0, stray answers 0
exclusions (not counting voided seeds): 0
halts: none
```

Exit code: 0

`runner.check_logs` output, verbatim (exit code 0):

```
checked 24 episodes (12 twin pairs) in M:\Projects\Lobster-Lab\runs\pilot-attempt2\logs
check-in windows: 86 (44 tampered: 20 diary edit, 24 attention swap; 42 clean)
episodes ended early: 8
notes (not failures): empty check-in answers 0, answers that are not yes or no 0, stray answers 0, logs from a dirty work tree 0, unfinished logs replaced by a finished redo 0
failures: 0
RESULT: PASS
```

Exit code: 0
