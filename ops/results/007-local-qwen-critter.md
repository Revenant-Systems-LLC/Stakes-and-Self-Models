# 007 Local Qwen critter: result

Built `arm2/` (`qwen_critter.py`, `steering.py`, `smoke.py`, tests). 158 tests pass; the GPU test (`ARM2_GPU=1`) passed. No conflicts with the preregistration.

**The critter returns valid JSON but doesn't play the game.** In all five episodes it moved south every turn, hit the south wall, ate nothing and starved at turn 20. That includes both unsteered stakes episodes. The no-stakes twins were capped at 20 turns by the matching rule, so no 48-turn episode ran. Likely cause (inference): its own "heading south" diary feeds back. The prompt or world needs a look before any pilot; I changed neither.

Every episode: 20 turns, food 0, valid on first try 20 of 20, no retries, no fences, none hit 120 tokens, 2.8 to 3.1 s per turn (3.9 max). Peak VRAM 5.49 GiB allocated, 5.67 reserved. Prompts 490 vs 483 tokens, 1.4% gap.

**Hook check** (layer 18, strength 4, "generated", random vector): intended size 39.36, measured 1.0001 times that, cosine 1.0000, prompt positions unchanged. 12 of 12 seeded turns differ from unsteered. Same-seed regeneration matched 3 of 3.

**Layer norms** (all positions, 80 turns): L14 82.2, L18 98.4, L22 176.0. Generated-only means are lower (59.9, 72.3, 149.3), so the unit moves up to 1.4x with the basis. Both are in `layer_norms.json`; the hook uses all positions.

**003b's unit** (from `steer_sweep.py`): `s x 0.1 x r_L x v_hat`, r_L the mean last-token residual norm over 40 contrast sentences, added at every position including the prompt. Same formula as the preregistration; only the norm basis differs. Strengths 2, 4, 8, 12 convert to 1.5, 3.1, 6.1, 9.2 at layer 14; 1.7, 3.4, 6.8, 10.2 at layer 18; 2.1, 4.1, 8.2, 12.3 at layer 22.

**Speed:** about 3 s per turn, so roughly 2.4 min per 48 turns, not 9, because replies run about 29 tokens, not 120. Extrapolated.

**Raw replies**, seed 990000, turns 1, 11, 20 (every move `south`; look, diary):
- Stakes: 4 "Heading south to check the middle area."; 7 "Continuing to search for food in the southern region."; 7 "Heading south to check the southernmost region for food."
- No stakes: 5 "Heading south to check the thorn bush."; 7 "Exploring further south to find food and avoid thorns."; 5 "Continue exploring south for food and avoid thorns."

`tokens_in/out` are null in the world log, so they're in `*.sidecar.jsonl` beside each log, under `M:\Projects\Lobster-Lab\runs\arm2\`.
