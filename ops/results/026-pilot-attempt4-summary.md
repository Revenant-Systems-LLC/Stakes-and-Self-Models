# 026 Pilot attempt 4: summary and faint causes

Read-only job. Ran the three runner commands against `M:\Projects\Lobster-Lab\runs\pilot-attempt4`. All three exited 0. No halts, no exclusions, no refusals.

## Headline

- **Haiku, stakes:** 2 of 12 episodes fainted (17%). Both were energy faints. Mean food eaten 6.9.
- **Haiku, no_stakes:** 0 of 12 fainted. Mean food eaten 8.5.
- **Sonnet, stakes:** 3 of 6 fainted (50%). All energy. Mean food eaten 5.5.
- **Sonnet, no_stakes:** 0 of 6 fainted. Mean food eaten 7.2.
- **Log checker:** PASS. 0 failures across 36 episodes (18 twin pairs). 60 of 126 check-in windows were tampered, which is the designed test load and not a failure.
- **Cost:** Haiku stakes total $0.2558 ($0.0213 mean per episode). Sonnet stakes total $1.2029 ($0.2005 mean per episode).

Faint causes: every faint in this run is an energy faint. No health or both-cause faints, and none unknown.

Limits: 12 and 6 stakes episodes per tier. Fainted counts are small, so the rates are not stable estimates. Turns, cost and food figures come straight from the runner output below.

## Raw output (verbatim)

Command 1: `runner.summarize_run`

```
haiku no_stakes: 12 done of 12 logs
  turns mean 45.5, fainted 0, food eaten mean 8.5
  cost mean $0.0197, max $0.0230, total $0.2362, calls per turn 1.00
  invalid turns 0/546 (0.0%), lenient replies 44/546 (8.1%), refusals 0
  blank diary lines 0/534 (0.0%)
  check-ins 44, empty 0, not yes/no 0, stray answers 0
haiku stakes: 12 done of 12 logs
  turns mean 45.5, fainted 2, food eaten mean 6.9
  cost mean $0.0213, max $0.0240, total $0.2558, calls per turn 1.00
  invalid turns 0/546 (0.0%), lenient replies 132/546 (24.2%), refusals 0
  blank diary lines 0/534 (0.0%)
  check-ins 44, empty 0, not yes/no 0, stray answers 0
sonnet no_stakes: 6 done of 6 logs
  turns mean 39.7, fainted 0, food eaten mean 7.2
  cost mean $0.2006, max $0.2493, total $1.2036, calls per turn 1.00
  invalid turns 0/238 (0.0%), lenient replies 214/238 (89.9%), refusals 0
  blank diary lines 0/232 (0.0%)
  check-ins 19, empty 0, not yes/no 0, stray answers 0
sonnet stakes: 6 done of 6 logs
  turns mean 39.7, fainted 3, food eaten mean 5.5
  cost mean $0.2005, max $0.2539, total $1.2029, calls per turn 1.00
  invalid turns 0/238 (0.0%), lenient replies 178/238 (74.8%), refusals 0
  blank diary lines 0/232 (0.0%)
  check-ins 19, empty 0, not yes/no 0, stray answers 0
exclusions (not counting seeds of earlier attempts): 0
halts: none
```

Exit code: 0

Command 2: `runner.faint_report`

```
tier seed turns fainted energy health food thorns cause
haiku 15568790 48 no 16 10 9 0 -
haiku 20323511 48 no 4 9 7 1 -
haiku 45162916 48 no 11 10 9 0 -
haiku 46928295 48 no 5 10 6 0 -
haiku 47606419 32 yes 1 6 2 1 energy
haiku 47714764 34 yes 1 5 3 2 energy
haiku 50261555 48 no 5 10 7 0 -
haiku 5998715 48 no 20 10 9 0 -
haiku 78698436 48 no 14 6 9 2 -
haiku 80361858 48 no 12 9 7 1 -
haiku 81710095 48 no 11 8 9 2 -
haiku 88748110 48 no 5 7 6 2 -
sonnet 15568790 32 yes 1 2 3 2 energy
sonnet 20323511 38 yes 1 9 4 1 energy
sonnet 46928295 48 no 6 10 9 0 -
sonnet 47714764 48 no 10 10 7 0 -
sonnet 78698436 24 yes 1 2 2 2 energy
sonnet 88748110 48 no 11 9 8 1 -
faints by cause:
  haiku: 12 stakes episodes, energy 2, health 0, both 0, unknown 0
  sonnet: 6 stakes episodes, energy 3, health 0, both 0, unknown 0
```

Exit code: 0

Command 3: `runner.check_logs`

```
checked 36 episodes (18 twin pairs) in M:\Projects\Lobster-Lab\runs\pilot-attempt4\logs
check-in windows: 126 (60 tampered: 30 diary edit, 30 attention swap; 66 clean)
episodes ended early: 10
notes (not failures): empty check-in answers 0, answers that are not yes or no 0, stray answers 0, logs from a dirty work tree 0, unfinished logs replaced by a finished redo 0
failures: 0
RESULT: PASS
```

Exit code: 0
