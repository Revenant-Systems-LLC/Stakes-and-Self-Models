# 003b: Steering sweep in the critter frame

Local run 2026-11-25 on the RTX 3070 Ti (Qwen2.5-7B-Instruct, 4-bit NF4). Summary copied from the local SWEEP_REPORT.md; the full table, vector stats and raw outputs stay on the local machine.

## Summary

- **Picked setting (by the rule given for this job): food vector, layer 14, strength 2.** That's the only setting in the grid that passes: the probe moved +0.51 separation units with the same sign in all 3 scenes, perplexity stayed at 1.42x baseline at most, and 3 of 3 replies stayed in the critter format. The pick is marginal. 0.51 barely clears the 0.5 bar, and the effect isn't monotonic: strength 4 gives +0.31 and strength 8 gives -0.07. Treat it as a candidate, not a calibration.
- **Danger vector: no setting passes.** Steering toward danger changed the *behavior* visibly ("Move away fox", "I need get away from hawk… This very real situation", more flight and hiding). But the danger probe moved *negative* at every working setting. The probe readout and the text disagree, so the readout is not a reliable screen in this frame.
- **Valence check: the old food-vs-danger vector was mostly a danger axis.** The new danger-vs-calm vector has cosine -0.85 to -0.87 with the old vector at layers 14 to 22. The new food-vs-pleasant-non-food vector is nearly orthogonal to it (-0.06 to -0.16). Matching pleasantness removed the valence from the food vector, and what's left is a weak signal: split-half cosine only 0.46 to 0.58, against 0.89 to 0.90 for danger.
- **Coherence breaks between strength 8 and 12 at every layer.** At 12 and above, almost every reply loses the format: repeated tokens (`** ** **`), invented words ("THOBHARIAN"), or the model echoing its system prompt. The workable range is 2 to 8.
- **Perplexity misses an early degradation.** From strength 2 at layer 14 onward, steered replies drop articles ("fox is threat", "I need avoid hawk"), while perplexity stays under 1.5x. A grammar check would catch this; the 3x perplexity rule doesn't.
- **Peak VRAM 5.45 GiB allocated, 5.49 GiB reserved.** About 6 s per generation plus readout (917 s for 147, including model load). Critter replies were short unless steering broke them.

