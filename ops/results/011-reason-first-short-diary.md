# 011 result

**No variant forages.** All 20 episodes (R0 to R4, dev seeds 990006 to 990009) fainted by turn 26. Best was 1 food in one episode (R0, R1, R4 each). Reason-first order and a shorter diary both failed.

```
     keys              diary  food/ep  faint turns   on food/ate  eats on empty  repeat lines
R0   diary,look,move   15     0.25     24,20,20,20   4/1          1              0.43
R1   R0, diary=plan    15     0.25     20,20,20,26   7/1          30             0.56
R2   R1                5      0.00     20,20,20,20   18/0         2              0.56
R3   R1                3      0.00     20,20,20,20   18/0         0              0.60
R4   move,look,diary   5      0.25     20,20,20,25   1/1          32             0.20
```
Valid JSON 100% everywhere. Moves, cells, per-episode rows: `M:\Projects\Lobster-Lab\runs\arm2\diag2\SUMMARY.md`.

**What changed:** the habit moved from south to north (R2: 71 of 80 moves), not toward the map. A shorter window didn't break the diary loop: the last 3 to 5 lines are the same line. R2 seed 990009 stood on food 16 turns and never ate. R1 and R4 eat on empty cells because "if food, eat" gets matched to food seen on the map.

**Turn-1 probe** (dev seeds 990030 to 990049, F directly north in view). P(north) as dealt vs food north: R1 0.523 vs 0.520, R2 0.659 vs 0.645. With food north: R1 north .52, east .45, south .03; R2 north .65, east .26, south .09; R4 (move first) south .64, north .007. The move ignores where the food is in every variant.

**Raw replies, R1:**
- 990008 t1, empty cell: `{"diary": "Moved to food, need to eat it.", "look": 4, "move": "eat"}` (same for 20 turns)
- 990009 t1: `{"diary": "Heading north to find food.", "look": 1, "move": "north"}`
- 990009 t8, on food: `{"diary": "Going north to find more food sources.", "look": 1, "move": "north"}`

**Amendments:** R2, R3, R4 need a dated diary-window amendment for every arm. R0 and R1 keep 15, but R1's reply example in `prompts/` is shared.

**Recommendation (80%; 20 episodes plus a 20-seed probe):** change nothing in `prompts/`, `world/` or the preregistration. Nothing here earns an amendment. Next test, if you want it: can Qwen2.5-7B answer a map question on its own, or is another model in hf_home worth trying.

Code: `arm2/diag2*.py`, `tests/test_diag2.py` (163 tests pass); defaults unchanged.
