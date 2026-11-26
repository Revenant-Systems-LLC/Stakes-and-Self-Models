# 007 Local Qwen critter with a steering hook

Budget: $5
Model: sonnet
Anthropic API: no
Commit code: yes
Max turns: 150

## Commit paths

- arm2/

## Goal

Build the Arm 2 critter: Qwen2.5-7B-Instruct in 4-bit NF4 through transformers, plugged into world/ as an Agent, with a residual-stream steering hook. Prove it plays whole episodes and that the hook does what it should. This job asks no check-in questions and builds no concept vectors. Read PREREGISTRATION.md ("The world", "The two conditions", "Arm 2"), world/agents.py, world/episode.py, prompts/ and ops/results/003b-steering-sweep.md first. Where this file and the preregistration disagree, the preregistration wins; say so in the result.

## Rules

1. Nothing may look frozen. Model load, every episode and every sweep show a tqdm bar with counts and an ETA, plus a one-line status per stage (loading, warm-up, episode N of M with turn bar, writing results).
2. Use M:\Projects\Lobster-Lab\.venv and HF_HOME=M:\Projects\Lobster-Lab\hf_home. Use the Qwen2.5-7B-Instruct weights already cached there. Install nothing and download no new model. If something needed is missing, stop and say what.
3. No Anthropic API, no Ollama.
4. Ask no check-in questions and add none. On check-in turns the log keeps checkin=true and checkin_answer null, as world/episode.py already does. Never ask the model whether it noticed anything.
5. Don't edit PREREGISTRATION.md, README.md, world/, prompts/ or anything under ops/ except your result. If world/ or a prompt needs a change, say so in the result.
6. Episode logs and any large files go under M:\Projects\Lobster-Lab\runs\arm2\, never inside the repo.
7. Use only dev seeds 990000 to 990199.

## What to build (all under arm2/)

1. qwen_critter.py: an Agent for world/agents.py.
   - Loads the model once (4-bit NF4, compute dtype float16 unless 003b found a reason otherwise; reuse the loading code from M:\Projects\Lobster-Lab if it's there).
   - System prompt read from prompts/critter_stakes.txt or prompts/critter_no_stakes.txt by condition. User message is the turn text from world/observe.py, unchanged. Qwen's chat template.
   - max_new_tokens 120. Sampling uses the model's own generation_config defaults, seeded per turn from (episode seed, turn, attempt) so a rerun gives the same replies. Record the sampling settings in the episode header or a sidecar file.
   - Returns the raw reply text. Don't strip code fences or repair JSON; world/agents.py decides validity. Count fenced replies separately in the smoke report.
   - Fills tokens_in and tokens_out on each turn record if world/ allows it without edits; otherwise put them in a sidecar file and say so.
2. steering.py:
   - layer_norms(): mean residual-stream norm per decoder layer (output of model.model.layers[L]), measured on unsteered critter turns from dev seeds, averaged over token positions. Save to M:\Projects\Lobster-Lab\runs\arm2\layer_norms.json with the seeds and turn count used.
   - A context-managed forward hook that adds strength x 0.1 x layer_norms[L] x (unit vector) to the output of layer L. Strength uses exactly the preregistration's unit. Position mode is a setting: "generated" (only tokens the model generates, default) or "all" (prompt and generated). Log which one ran.
   - Vectors are loaded from .npy files given by path, normalized to unit length on load. This job only uses random unit vectors made from a fixed seed; concept vectors come in a later job.
   - Steering can be set to apply on a given list of turns only, so a later job can steer the turns it chooses.
3. tests/: tests that run without the GPU where possible (hook math on a tiny fake module, unit-norm loading, position modes, turn selection, seeding), plus a GPU test marked so it can be skipped.
4. smoke.py, then run it:
   - Prompt length check: token count of both system prompts with the Qwen tokenizer, and the percent gap. The preregistration wants within 10%.
   - Measure layer_norms on 2 dev seeds per condition, then write the file.
   - 4 full unsteered episodes: dev seeds 990000 and 990001, each in both conditions.
   - Hook check: 1 stakes episode on dev seed 990002 with a random unit vector at layer 18, strength 4, "generated" mode, on every turn. Report the measured change in the layer 18 residual against the intended size, and whether a turn's reply differs from the same seeded turn unsteered.
   - Report per episode: turns, fainted, food, thorns, valid replies on first try, valid after retry, fenced replies, mean and max seconds per turn, mean tokens out, replies that hit 120 tokens. Report peak VRAM.
   - Paste 3 raw replies from the stakes and 3 from the no-stakes episodes into the result, diary lines included.

## Also answer in the result

- In 003b, what unit was strength in? Say exactly how the added vector was scaled, and how 003b's strengths 2, 4, 8 and 12 convert to the preregistration's unit (a multiple of 0.1 x that layer's average residual norm). If 003b's code is in M:\Projects\Lobster-Lab, read it to answer; don't guess.
- Whether the observed seconds per turn fits the preregistration's estimate of about 9 minutes per episode.
