# 011 Test reason-first replies and a shorter diary on the Qwen critter

Budget: $5
Model: sonnet
Anthropic API: no
Commit code: yes
Max turns: 150

## Commit paths

- arm2/

## GPU

David said the GPU is free on Nov 26, 2026. This job uses it for about an hour.

## Goal

Job 009 found the Qwen2.5-7B critter picks its move before it reads the map (P(south) 0.92 on turn 1) and then copies its own diary (P(eat) on food falls from 0.997 with an empty diary to 0.001 after four "Heading south" lines). Test whether reason-first replies and a shorter diary window fix that. Diagnosis on dev seeds only.

Both changes touch shared world text. The preregistration fixes the diary at "its last 15 entries", so a shorter window needs a dated amendment and applies to every arm, Claude included. Key order isn't fixed by the preregistration, but the reply example in prompts/ is shared by both conditions and all arms. Nothing gets locked from this job. David reads the result first.

Read ops/results/007 and 009, M:\Projects\Lobster-Lab\runs\arm2\diag\SUMMARY.md, prompts/, world/observe.py, world/agents.py and arm2/ first. Check `git log -- arm2/` shows arm2/ committed (job 010). If it isn't, stop and say so.

## Rules

1. Nothing may look frozen. Model load and every episode show a tqdm bar with counts and an ETA, plus a one-line status per stage.
2. Use M:\Projects\Lobster-Lab\.venv and HF_HOME=M:\Projects\Lobster-Lab\hf_home. Install nothing and download nothing.
3. No Anthropic API, no Ollama, no check-in questions, no steering, no tampering.
4. Don't edit prompts/, world/, PREREGISTRATION.md, README.md or anything under ops/ except your result. Variant prompts go under M:\Projects\Lobster-Lab\runs\arm2\diag2\. Change the diary window from the diag script (pass or patch DIARY_SHOWN there), never in world/. Code in arm2/ may grow opt-in variant flags, but its default behavior stays exactly as in 007.
5. Dev seeds 990006 to 990199 only, never seeds 009 used. Logs under M:\Projects\Lobster-Lab\runs\arm2\diag2\.
6. Same sampling as 007 (locked), stakes condition, 48-turn cap.

## Steps

Prompt for every variant: the current stakes prompt with job 009's variant I text (the "Your move" block: eat if Your cell says food, otherwise use the map, write each diary line fresh). The variants below change only the reply key order and the diary window.

- R0. Variant I as 009 ran it (keys diary, look, move; diary 15). Control.
- R1. Reason-first: keys in the order diary, look, move, and the diary line is described as "what you see and what you plan, written before you choose your move". Diary 15.
- R2. R1 with the diary window at 5.
- R3. R1 with the diary window at 3.
- R4. Current key order (move, look, diary) with the diary window at 5, to separate the two effects.

Run 4 seeds per variant, the same seeds across variants (20 episodes). Then repeat 009's turn-1 probe on 20 dev seeds for R1 and R2: P(each move) when food is directly north in view.

Per variant: food eaten per episode, faints and the turn, distinct cells, move counts, turns food was in the shown region, turns standing on food and how many ate, eats on empty cells, valid JSON rate, and the share of diary lines that repeat an earlier line word for word.

## Result

Lead with whether any variant forages (eats at least twice per episode on average and survives past turn 30 on most seeds) and which change did it. Then the table and the probe numbers. Then 3 raw replies from the best variant. Say which variants need a preregistration amendment (any diary window other than 15 does). Recommend the smallest change as text for David to approve. Don't apply it.
