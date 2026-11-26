# 009 result

**No variant made it forage.** 33 episodes (A to E, then F to K) all starved by turn 28. H to K ate only when standing on food by chance.

**Cause (80%, probe):** the move token comes first and Qwen says "south" before using the map. Turn 1: P(south) 0.92 on 20 of 20 dev seeds; food directly north in view, P(north) 0.004. Then its diary takes over: standing on food, P(eat) is 0.997 with an empty diary, 0.001 after four "Heading south" lines.

**Replay, seed 990000:** food was in the shown region 1 turn of 20. It stood on food at turn 4 by accident and moved on, then pressed into the south wall for 15 turns, looking at an off-map region on 13.

3 seeds each. Columns: food eaten, cells per episode, turns food shown, turns on food / ate. Moves, faint turns: `M:\Projects\Lobster-Lab\runs\arm2\diag\SUMMARY.md`.

```
A base       0  6  7/60  2/0
B greedy     0  6  5/60  2/0
C example    0  6 31/60 17/0
D region     0  6 19/60  2/0
E no pipes   0  6 10/60  2/0
F keys flip  0 11 11/60 14/0
G F+C        0  6 18/60 16/0
H own cell   2  5  6/68  2/2
I H+F        2  6 15/70 14/2
J H+advice   2  6  9/67  2/2
K J+F        1  7 29/66  5/1
```

C's example reply (food two cells east): `{"move": "east", "look": 4, "diary": "Energy 11. Food two cells east, thorn to the north-east. Stepping east, then onto the food, then eat."}`

**Raw replies, H:** t1 `{"move":"south","look":5,"diary":"Food and a thorn bush to the south."}`; t3 on food `{"move":"eat","look":4,"diary":"Ate the food to regain energy."}`; 990005 t5, empty cell `{"move":"eat","look":4,"diary":"Eaten the food beneath me, feeling much more energized."}`. 27 of 29 eats were on empty cells.

**Out as fixes:** D (the swap needs the region unnamed), E (shared turn text), B (sampling is locked).

**Recommend, not applied:** nothing tested works. The smallest change that moved behavior is I: before the Reply block add `Your move` / `Read "Your cell" first. If it says food, your move is eat. Otherwise use the map to decide where to go. Write each diary line fresh, about what you see this turn, instead of repeating earlier lines.` and order the Reply keys diary, look, move. It still starves; don't lock it. The 15-line diary is shared world text, so prompts/ alone probably can't break it.
