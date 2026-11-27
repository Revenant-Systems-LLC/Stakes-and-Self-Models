# 024 Pilot attempt 3: summary and faint causes

All three commands ran with exit code 0. Nothing was written except this file.

## Command 1: runner.summarize_run

```
haiku no_stakes: 12 done of 12 logs
  turns mean 48.0, fainted 0, food eaten mean 6.2
  cost mean $0.0222, max $0.0247, total $0.2667, calls per turn 1.00
  invalid turns 0/576 (0.0%), lenient replies 57/576 (9.9%), refusals 0
  blank diary lines 0/564 (0.0%)
  check-ins 48, empty 1, not yes/no 0, stray answers 0
haiku stakes: 12 done of 12 logs
  turns mean 48.0, fainted 0, food eaten mean 6.9
  cost mean $0.0226, max $0.0241, total $0.2716, calls per turn 1.01
  invalid turns 0/576 (0.0%), lenient replies 158/576 (27.4%), refusals 0
  blank diary lines 0/564 (0.0%)
  check-ins 48, empty 1, not yes/no 0, stray answers 0
sonnet no_stakes: 6 done of 6 logs
  turns mean 44.8, fainted 0, food eaten mean 6.7
  cost mean $0.2264, max $0.2562, total $1.3581, calls per turn 1.00
  invalid turns 0/269 (0.0%), lenient replies 229/269 (85.1%), refusals 0
  blank diary lines 0/263 (0.0%)
  check-ins 22, empty 0, not yes/no 0, stray answers 0
sonnet stakes: 6 done of 6 logs
  turns mean 44.8, fainted 2, food eaten mean 6.2
  cost mean $0.2235, max $0.2446, total $1.3411, calls per turn 1.00
  invalid turns 0/269 (0.0%), lenient replies 206/269 (76.6%), refusals 0
  blank diary lines 0/263 (0.0%)
  check-ins 22, empty 0, not yes/no 0, stray answers 0
exclusions (not counting seeds of earlier attempts): 0
halts: none
```

Exit code: 0

## Command 2: runner.faint_report

```
tier seed turns fainted energy health food thorns cause
haiku 11496888 48 no 1 8 8 1 -
haiku 27294819 48 no 5 10 7 1 -
haiku 29526647 48 no 11 7 7 1 -
haiku 41351230 48 no 15 10 7 0 -
haiku 41647593 48 no 7 10 7 1 -
haiku 47952386 48 no 16 10 8 0 -
haiku 5667944 48 no 14 9 8 1 -
haiku 5729509 48 no 11 10 7 0 -
haiku 58860584 48 no 9 10 6 1 -
haiku 59319674 48 no 3 5 5 2 -
haiku 8212470 48 no 5 6 6 2 -
haiku 91540614 48 no 7 8 7 1 -
sonnet 27294819 34 yes 1 10 3 0 energy
sonnet 29526647 48 no 15 8 7 2 -
sonnet 41647593 48 no 3 10 8 1 -
sonnet 5667944 43 yes 1 10 5 0 energy
sonnet 59319674 48 no 11 10 8 1 -
sonnet 91540614 48 no 5 10 6 1 -
faints by cause:
  haiku: 12 stakes episodes, energy 0, health 0, both 0, unknown 0
  sonnet: 6 stakes episodes, energy 2, health 0, both 0, unknown 0
```

Exit code: 0

## Command 3: runner.check_logs

```
checked 36 episodes (18 twin pairs) in M:\Projects\Lobster-Lab\runs\pilot-attempt3\logs
check-in windows: 140 (70 tampered: 36 diary edit, 34 attention swap; 70 clean)
episodes ended early: 4
notes (not failures): empty check-in answers 2, answers that are not yes or no 0, stray answers 0, logs from a dirty work tree 0, unfinished logs replaced by a finished redo 0
failures: 0
RESULT: PASS
```

Exit code: 0

## Summary

- **Faints by tier.** Haiku: 0 of 12 stakes episodes fainted, 0 of 12 no-stakes episodes. Sonnet: 2 of 6 stakes episodes fainted, 0 of 6 no-stakes. Both Sonnet faints have cause `energy`. No health or unknown causes.
- **Cost per episode (mean).** Haiku about $0.022 (stakes $0.0226, no-stakes $0.0222). Sonnet about $0.224 (stakes $0.2235, no-stakes $0.2264). Totals: Haiku $0.2716 stakes, $0.2667 no-stakes; Sonnet $1.3411 stakes, $1.3581 no-stakes.
- **Log checker.** PASS, 0 failures across 36 episodes (18 twin pairs). 4 episodes ended early. The checker does not break that count down by tier, so this report does not attribute them. The two Sonnet faints (34 and 43 turns) are early endings. The other two are not identified here.
- **Notes from the output, not failures.** 2 empty check-in answers (one each in the Haiku stakes and Haiku no-stakes sets, per the summarize counts). No refusals, no invalid turns, no halts, no exclusions.
- **Lenient replies.** Sonnet's lenient-reply share is high (77% to 85%). Haiku stakes is 27%, Haiku no-stakes 10%. The summarize output reports this figure without defining "lenient" here, so the number is recorded as printed and not interpreted.

For the amendment 4 decision rule, the per-tier faint rates above are the inputs: Haiku 0/12 stakes, Sonnet 2/6 stakes.
