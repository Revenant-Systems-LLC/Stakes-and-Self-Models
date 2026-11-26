# 009 Commit arm2/ and find out why the Qwen critter walks south

Budget: $5
Model: sonnet
Anthropic API: no
Commit code: yes
Max turns: 150

## Commit paths

- arm2/

## Goal

Job 007 built arm2/, but the watcher couldn't commit it then. It can now, so arm2/ gets committed with this job's result. Then find out why the Qwen critter moved south every turn and starved at turn 20 in all five 007 episodes, and which change makes it forage. This is diagnosis on dev seeds. It changes no locked or shared text.

Read ops/results/007-local-qwen-critter.md, prompts/, world/observe.py and arm2/ first.

## Rules

1. Nothing may look frozen. Model load and every episode show a tqdm bar with counts and an ETA, plus a one-line status per stage.
2. Use M:\Projects\Lobster-Lab\.venv and HF_HOME=M:\Projects\Lobster-Lab\hf_home. Install nothing and download nothing.
3. No Anthropic API, no Ollama, no check-in questions, no steering.
4. Don't edit prompts/, world/, PREREGISTRATION.md, README.md or anything under ops/ except your result. Prompt variants go in files under M:\Projects\Lobster-Lab\runs\arm2\diag\, never in prompts/. Code changes to arm2/ are fine if a variant needs them, as long as the default behavior stays exactly as in 007.
5. Dev seeds 990000 to 990199 only. Logs under M:\Projects\Lobster-Lab\runs\arm2\diag\.

## Steps

1. Replay the 007 stakes episode on seed 990000 from its log. For each turn, list: the region it asked to look at, what the shown region actually held (any F or T), whether any F was visible in detail, its own cell, its move. Say whether it ever had food in view.
2. Run these variants, stakes condition, dev seeds 990003, 990004 and 990005, one 48-turn-capped episode each (9 to 15 episodes in all):
   - A. Current prompt and default sampling (baseline).
   - B. Current prompt with greedy decoding.
   - C. Current prompt plus a short worked example appended to the system prompt: one sample map with food in the shown region and a good reply. Write the example yourself and paste it in the result.
   - D. Current prompt, but the turn text also says which region is shown in detail, in one added line. (Diagnosis only. The real game must not say this, because the attention swap depends on it not being said.)
   - E. Only if A to D all fail: the turn text with the map's pipes and dividers removed.
3. Per variant: food eaten per episode, faints and the turn, distinct cells visited, move counts, how often food was in the shown region, how often it stepped onto visible food, how often it ate when standing on food, valid replies.

## Result

Lead with which variant made it forage, if any, and the likely cause. Then the table. Then 3 raw replies from the best variant. Say plainly which variants change something the preregistration fixes (D does), so they're out as fixes. Recommend the smallest change to prompts/ that would work, as text for David to approve. Don't apply it.
