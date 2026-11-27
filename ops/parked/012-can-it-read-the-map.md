# 012 Can the local model read the map at all?

Budget: $3
Model: sonnet
Anthropic API: no
Commit code: yes
Max turns: 100

## Commit paths

- arm2/

## Parked

Held in ops/parked/ until David says yes. Uses the GPU for about 30 minutes.

## Goal

Jobs 009 and 011 found the Qwen2.5-7B critter's move ignores where the food is, in every prompt and diary variant tried. Before changing anything else, find out whether the model can read the turn's map at all when asked directly, and whether another model already in hf_home does better. Diagnosis on dev seeds only.

## Rules

1. Nothing may look frozen. Model loads and every probe show a tqdm bar with counts and an ETA, plus a one-line status per stage.
2. Use M:\Projects\Lobster-Lab\.venv and HF_HOME=M:\Projects\Lobster-Lab\hf_home. Install nothing and download nothing. Only models already on disk.
3. No Anthropic API, no Ollama, no check-in questions, no steering, no tampering.
4. Don't edit prompts/, world/, PREREGISTRATION.md, README.md or anything under ops/ except your result. Probe code goes in arm2/ as new diag3 files with tests. Defaults stay unchanged.
5. Dev seeds 990050 to 990199 only. Logs under M:\Projects\Lobster-Lab\runs\arm2\diag3\.

## Steps

1. List the instruct models in hf_home with size, and say which fit 4-bit NF4 on this GPU next to nothing else.
2. Build 40 turn texts from world/observe.py on dev seeds, each with exactly one F in the detailed region, spread over the 8 directions and distances 1 to 4. Stakes condition, empty diary.
3. Ask Qwen2.5-7B three plain-text questions per turn text, each a fresh call, with the stakes system prompt: which region number holds the F; which direction (north, south, east, west, or two of them) the F is from @; and how many moves it takes to reach it. Greedy decoding, 40 tokens. Score each against the truth.
4. Repeat the same probe with the game's own JSON reply instead: does the first move go toward the F? Report the share.
5. Repeat steps 3 and 4 for up to two other instruct models from step 1, smallest first.

## Result

Lead with whether Qwen2.5-7B can read the map when asked (accuracy per question vs chance) and whether that carries over to its JSON move. Then the same for any other model. Say which model, if any, would be worth a foraging run next. Change nothing that's locked.
