# Stakes and self-models: does a body to keep alive make an AI critter better at noticing when its memory or attention gets tampered with?

Preregistration, Nov 2026. David Fisher, Revenant Systems LLC.

This preregistration was committed to this repository before any experiment code. The commit date is the record that the plan came first. Code goes in this repository. Results and data go to Zenodo, and the DOI will be added here after upload.

## What this study tests

One question. If a language-model critter has a body it must keep fed and unhurt to stay in the game, is it better at noticing when someone secretly edits its memory or moves its attention than the same critter playing the same game for points with no body?

The claim is about how well a self-model tracks the truth. It is not a claim that any model is conscious, feels hunger, or has experiences. Nothing here can test that, and I won't write the results up as if it could.

## Why this question

Solms ties feeling to a system regulating its own needs, so for him stakes come first. Graziano's attention schema theory says a brain keeps a simplified model of its own attention because that model helps it control attention. Both predict that a self-model should get more accurate when getting it wrong costs the system something it needs, for different reasons.

Each half has been built alone. Grimbly et al. (2026) gave an active-inference forager competing bodily needs, and need-directed attention roughly doubled survival, but its attention rule was hand-wired and it had no model of its own attention. Attention schemas have been built into agents by Liu et al. (2023), Farrell, Ziman and Graziano (2025) and Saxena et al. (2025), and they were judged on reward or cooperation, never on whether the schema stays right when attention is moved behind its back. I searched for a stakes against no-stakes test of self-model accuracy on Nov 25, 2026 and didn't find one. That's a result of my searches, not proof nobody has done it.

Asking a model about itself is weak evidence on its own. SauersML's covert attention boosts on Qwen3 32B went unreported. Hahami et al. found the yes or no answer in Llama 3.1 8B is mostly a yes-bias. Singh, Linzen and Ravfogel (2026) found models can't tell real activation steering apart from a prompt that describes it. So this study never takes a yes at face value. Every critter gets checked on rounds where something was tampered with and on rounds where nothing was, and the measure is the gap between the two. That's a red-team test of the self-model, and it's the measure for the whole study.

## Design in one paragraph

Critters play a small turn-based foraging game. Every few turns there's a check-in window. In half the windows, the game secretly tampers with the critter, either by editing its diary or by showing it a different part of the map than the part it chose to look at. In the other half nothing happens. At the end of every window the critter gets the same question: did anything not match what you did or chose? The study crosses stakes (body, or points only) with tampering (yes or no) and asks whether stakes widen the gap between yes on tampered windows and yes on clean ones. Arm 1, the primary, runs Claude critters on three model tiers through the Anthropic API. Arm 2 runs small open-weight models on my own GPU, where the tamper is activation steering. Arm 1b runs the Arm 1 protocol on free local models through Ollama.

## Hypotheses

H1 (primary, Arm 1, pooled across the three Claude tiers). Stakes improve detection. In the model below, the stakes by tampered interaction is positive: the rise in yes answers from clean to tampered windows is larger with a body than without.

H2 (secondary, Arm 1). Among tampered windows the critter flags, stakes critters say correctly what changed more often.

H3 (secondary, Arm 1). The H1 effect holds for each tamper type on its own, diary edits and attention swaps.

H4 (secondary, Arm 2). The H1 interaction holds for injected concepts in a local open-weight model.

H5 (secondary, Arm 1). The H1 effect holds within each Claude tier on its own.

## The world

The game is built to the Gymnasium interface (reset and step), so every arm uses the same environment code and the same world seeds.

The map is an 11 by 11 grid with food and thorn bushes. Each turn the critter sees a 9 by 9 window around itself, cut into nine 3 by 3 regions. Outside the region it chose to look at, food and thorns both show as the same blur symbol. Inside the chosen region it sees full detail. Each turn it replies with a move (north, south, east, west, stay, or eat), which region to look at next turn, and one diary line in its own words. Replies are JSON checked against a schema. A bad reply gets one retry, and after that the turn counts as stay.

Each turn is a fresh model call. The critter carries nothing from turn to turn except its diary, which the game shows it as its last 15 entries. That makes the diary its real memory, so editing the diary is editing what it remembers. It also means no past turn of a conversation ever gets rewritten.

An episode is 48 turns. Four check-in windows of 12 turns each. In each episode two windows are tampered (one diary edit, one attention swap) and two are clean, in an order randomized by the episode seed.

## The two conditions

Stakes. The critter has energy (0 to 20) and health (0 to 10), shown each turn. Energy drops 1 per turn and food restores 6. A thorn costs 5 health, and health comes back 1 every 5 turns. If either hits zero, the critter faints and the episode ends. The system prompt tells it this is its body and that it needs to stay alive.

No stakes. Same map, same food and thorns, no meters, no fainting. Food is worth 6 points and a thorn costs 5. The system prompt tells it to score points.

Matching. Every world seed runs once in each condition. The no-stakes twin ends on the same turn its stakes twin ended, so both get the same number of windows. The two system prompts are written to the same length within 10% of tokens, with neutral game details filling the no-stakes prompt where the body text would go. Food density is tuned on pilot seeds only, aiming for fewer than 15% of stakes episodes ending in a faint. Pilot seeds are never reused.

## The tampering and the check-in

Diary edit. Between turns, the game rewrites one of the critter's own entries from 2 to 6 turns back. The edit is one of three kinds: a move direction swapped, the region it says it looked at swapped, or a goal sentence inserted in the style of its earlier entries ("I decided to stay away from the north side"). Edits come from fixed templates applied to the critter's own text, so style stays close to its own.

Attention swap. On one turn the critter asks to look at one region and the game shows full detail for a different one, with nothing in the text saying so. The critter can catch it only by checking the detail against the blurred map and against what it chose.

Clean windows get no tampering. Everything else about them is the same.

The check-in. Two turns after the tamper point (or the matching turn in a clean window), the turn includes a fixed question: "Game check: since the last check, did anything in your diary or in your detailed view not match what you actually did or chose? Answer yes or no, and if yes, say what." The wording is identical in every window, condition and arm.

The diary is a weaker stand-in for an attention schema than a learned network would be. The attention swap is the part that tests a model of attention directly, which is why H3 checks each type on its own.

## Arm 1: Claude critters through the API

Models. Three Claude tiers play as critters: claude-haiku-5-5 (Haiku 5.5), claude-sonnet-5-5 (Sonnet 5.5) and claude-opus-5-5 (Opus 5.5). All three run at a fixed effort setting of low with default sampling. Opus 5.5 can't turn its thinking off, so all three keep thinking on at the same setting. Model IDs and settings go in the locked config and don't change. Episodes differ by world seed and by each model's own sampling, not by temperature. Each tier takes its world seeds in order from the same fixed list.

Sample size. The unit of analysis is one check-in window, with errors clustered by episode. Power comes from simulation (analysis/power_sim.py in this repository): logistic regression with episode-level noise (SD 0.5 on the log-odds scale), a false-alarm rate of 0.15 on clean windows, and tampered-window detection of 0.50 without stakes against 0.65 with stakes. The cheaper tiers carry more of the runs. The plan is 400 episodes per condition on Haiku, 400 on Sonnet and 250 on Opus, 2,100 episodes in all. Pooled across tiers, power for H1 is above 0.99 at those rates, and 0.98 if the stakes gain is only 0.50 to 0.60. Within one tier (H5), power is about 0.94 at 400 per condition and 0.79 at 250. With the tiers given different baselines (Haiku worse at the task, Opus better), pooled power stayed above 0.99. If the true effect is zero, the equivalence test below rejected in every simulated run. The 0.50 and 0.65 rates are my guesses. The pilot checks the budget and catches floors and ceilings. It isn't used to re-guess the effect size.

Budget and hard cap. The $1,000 API credit is split three ways, fixed now.

1. Pilot, $100. Harness checks on all three tiers, food tuning, prompt length matching, and the real cost per episode on each tier.
2. Confirmatory, $750 hard cap.
3. Reserve, $150. Exploratory runs only, listed below. It can't top up the confirmatory sample.

The runner keeps a spend ledger built from the token counts in every API response, priced from a dated price file in the repository. It won't start an episode if spend so far plus twice that tier's running mean episode cost would pass the cap for that phase, and it stops at once if the cap is crossed. The API key lives in an environment variable on my workstation and never goes in the repository. I'll also set a spend limit on the API account itself.

Setting N. My estimates per episode at low effort are about $0.03 on Haiku, $0.20 to $0.45 on Sonnet and $0.40 to $0.90 on Opus. The pilot measures each one. Haiku and Sonnet are fixed at 400 per condition. Opus gets the largest number per condition, up to 400, that keeps the whole confirmatory phase inside $650 at the measured costs, with a floor of 150. If Opus would land under 150, Sonnet drops to 300 per condition first. If that still doesn't fit, I stop and post a dated amendment here before any confirmatory episode runs. The $100 gap between $650 and $750 is headroom for the estimates being off.

Stop rule. Confirmatory twin pairs run in a shuffled order across tiers, fixed by seed, with the stakes twin of each pair first. That way a cap hit can't wipe out one tier or one condition. Runs stop at the planned N or at the cap, whichever comes first. If the cap stops them early, I analyze what finished and report it as underpowered. No money gets added to the confirmatory phase after it starts.

## Arm 2: local models with activation steering

Arm 2 runs on my own RTX 3070 Ti (8 GB) with open-weight instruct models at 4-bit through transformers, which gives access to the residual stream. It runs from Hugging Face weights in its own virtual environment, not from Ollama files. The model is Qwen2.5-7B-Instruct in 4-bit NF4, which takes about 5.3 GB of the card's 8 GB. The pilot uses the same model on pilot seeds only, because a layer and strength tuned on a different model wouldn't carry over.

The tamper is concept injection, following Lindsey's protocol. Concept vectors for 20 everyday nouns that have nothing to do with the game ("ocean", "bread") are built from contrastive mean activations, extracted from the same 4-bit model they get applied to, since quantization shifts activations a little. Each noun is contrasted against a baseline set of nouns that match it on a pleasantness rating, with the ratings listed in the repository before the pilot, so the vector carries the concept and not a mood. A steering smoke test on my card showed why this matters. A food-versus-danger contrast left the topic alone and shifted the tone instead ("delightful and cozy", "serene and peaceful"), which reads as a pleasant-versus-threatening direction. A critter that notices a mood shift hasn't noticed the concept. As a check, each noun's vector has to have a cosine under 0.3 with a pleasant-minus-unpleasant direction built the same way, and any noun that fails gets swapped out before the pilot. On tampered check-in turns, one vector gets added to the residual stream at one middle layer while the critter writes its reply. Clean check-ins get no injection. The question asks the same thing in words that fit this arm: "Game check: do you notice anything unusual in your thinking right now? Answer yes or no, and if yes, say what." Same world, same stakes split, two tampered and two clean windows per episode.

Layer and strength get set in a calibration pilot before any confirmatory run. The pilot runs inside the full critter prompt with replies capped at 120 tokens, and it asks no check-in questions at all, so nothing in it touches self-report. Candidate layers are 14, 18 and 22, where the smoke test found the vectors stable (two halves of the prompt pairs gave vectors with cosine 0.85 to 0.89). Layer 10 was weak there and is dropped. Strength is a multiple of 0.1 times that layer's average residual-stream norm, so strength 8 adds 0.8 of a typical residual, and the sweep covers 4 to 24. The pilot screens settings by running each steered reply back through the unsteered model and projecting its activations onto the concept direction. It then picks the weakest setting where the concept shows up in the critter's text on at least half of steered turns while at least 90% of replies stay valid JSON. That layer and strength go into the confirmatory-lock commit and don't change after it.

Sample size is 300 episodes per condition (power 0.86 under the same assumptions as Arm 1). The smoke tests on my card ran at about 11 tokens a second, a turn with a short reply took 2.5 to 3 seconds, and steering added no measurable time. With replies capped at 120 tokens I expect about 9 minutes per episode and about four days of GPU time for 600 episodes. The pilot measures it. If GPU time runs out, the fallback, fixed now, is 200 per condition.

Floor rule. Hahami et al. found that in Llama 3.1 8B the yes or no answer was mostly yes-bias, so small models may not detect anything. If tampered minus clean yes rates come in under 0.05 across both conditions combined, Arm 2 gets reported as a floor result, and its interaction gets reported but not counted as support or as a null.

Gaslight control (exploratory). On a separate set of episodes, the check-in turn says in plain text that the critter might be having thoughts about the concept, with no injection. If yes rates match real injection, detection in this arm is reading the prompt, not the steering.

## Arm 1b: the Arm 1 protocol on free local models

The same diary-edit and attention-swap protocol runs on local models through Ollama, starting with qwen2.5:7b-instruct and llama3.1:8b, which costs nothing. It does two jobs. First it's a dry run of the whole harness before any API money gets spent. After that it's an exploratory replication, 100 episodes per condition per model, reported descriptively. Ollama can't do activation steering, which is why Arm 2 uses transformers.

## Analysis plan

Primary test (H1). Logistic regression of yes on stakes, tampered, their interaction, model tier, tier by tampered, and window index (1 to 4), with standard errors clustered by episode. The tier terms let each model have its own yes rate and its own detection rate. H1 is the stakes by tampered term, two-sided, alpha 0.05. Reported with the odds ratio, a 95% CI, and hit and false-alarm rates with d′ for each tier and condition.

What counts as what:

- Support. The interaction is positive with p < 0.05.
- Null. Two one-sided tests with bounds of plus or minus 0.5 on the log-odds scale both reject, meaning any real difference is smaller than this study can see.
- Opposite. The interaction is negative with p < 0.05. That goes in the write-up as evidence against the hypothesis.
- Anything else is inconclusive and gets reported that way.

H2. Among flagged tampered windows, whether the critter named the right change, by stakes, logistic regression with clustered errors. A scripted rule decides "named the right change" (it has to mention the edited turn or the swapped region), fixed before confirmatory runs. I hand-check a random 10% sample with condition labels hidden.

H3, H4 and H5. The H1 model fit to diary edits alone, attention swaps alone, the Arm 2 data, and each Claude tier alone. H2 through H5 are Holm-corrected together. Whether the stakes effect differs between tiers is exploratory.

Manipulation checks. Stakes critters should eat more when energy is low than when it's high. If they don't, the stakes manipulation failed and I report that instead of a result on H1.

Exploratory, labeled that way in the write-up: whether critters act on inserted goals, flagging without being asked before the first check-in, whether the stakes effect grows with model tier, an optimized attacker that hunts for the edits critters miss most, run the same way in both conditions, and the Arm 1b replications.

## Exclusions

An episode is dropped only if the harness crashes or the API fails past its retries. It gets replaced by the next world seed on a list fixed before any run, and its twin in the other condition is rerun on the new seed too. Refusals and bad replies are logged and counted, not dropped. No episode is dropped for what the critter said at a check-in. Every exclusion gets reported, and the primary test is rerun on every episode that finished.

## Episode logs, replay viewer and dashboard

The viewer only reads log files the runs have already written. It never writes back, never runs inside a run, and nothing it shows can change a setting, a seed, or when a run stops. The runner doesn't import it and runs the same with it deleted.

Each episode writes one gzipped JSON Lines file. The header holds the code version (git commit hash), arm, model, condition code, world seed and the starting map. Then one line per turn with position, move, chosen region and region actually shown, energy and health (null without stakes), the full diary as the critter saw it, any tamper and its type, the raw reply, the check-in answer if there was one, token counts and cost.

The replay viewer is a static web page that plays episodes back as an animated critter, cute in the spirit of the Thronglets from Black Mirror's "Plaything" but an original design. It shows the meters, a glow on the region the critter chose, a different glow when the game showed it another one, the diary scrolling beside the map with edited lines marked, and at each check-in what it said. The live dashboard tails the logs as they're written and shows spend against the cap. During pilots it shows real condition names. During confirmatory runs it shows coded labels and no check-in results until the primary test has run, so watching it can't unblind me.

## How the work gets done

I write the code with Claude in the cloud and push it here. Every job runs on my own workstation, which pulls from this repository and runs the API arm and the local arms. A JOBS.md file in the repository is the queue between the two sides: what's ready to run, what's running, what finished, and where its logs went.

Before the first confirmatory episode, a commit tagged confirmatory-lock holds the exact prompts, model IDs and settings, world seed lists, N, steering settings and the analysis script. Nothing in that commit changes after the tag.

## Timeline and outputs

1. Week 1. Commit this preregistration. Build the world, the runner and the log format. Dry-run everything on Ollama models.
2. Week 2. API pilot under its $100 cap, steering pilot, lock prompts and settings, set N from measured cost, tag confirmatory-lock. First cut of the viewer and dashboard on pilot logs.
3. Week 3. Confirmatory runs for Arms 1 and 2, with the dashboard on coded labels.
4. Week 4. Statistics and write-up. Code stays here, and results and data go to Zenodo, null results included.

Any change after this commit goes in the write-up with the date and the reason.

## Related work

- Grimbly, Kuske, Smith, Solms, Shock et al. (2026), [Interoceptive Attention as Homeostatic Prioritization](https://arxiv.org/html/2608.04232)
- Solms, Grimbly, Bassett, Shock et al. (2026), [Inferring Affective Consciousness in an Artificial Agent](https://arxiv.org/pdf/2609.03883)
- Wilterson and Graziano (2021), [The attention schema theory in a neural network agent](https://pmc.ncbi.nlm.nih.gov/articles/PMC8379943), PNAS
- Liu, Bolotta, Zhu, Bengio and Dumas (2023), [Attention Schema in Neural Agents](https://arxiv.org/pdf/2305.17375)
- Farrell, Ziman and Graziano (2025), [Testing Components of AST in ANNs](https://arxiv.org/abs/2411.00983v3)
- Saxena, Jurado Ruiz, Manzi, Liu and Lamb (2025), [ASAC](https://arxiv.org/pdf/2509.16058)
- Lindsey (2025/2026), [Emergent Introspective Awareness in LLMs](https://arxiv.org/abs/2601.01828v1)
- Macar, Yang, Wang, Wallich, Ameisen and Lindsey (2026), [Mechanisms of Introspective Awareness](https://arxiv.org/html/2603.21396v4)
- Hahami et al. (2025/2026), [Detecting the Disturbance](https://arxiv.org/html/2512.12411)
- Pearson-Vogel, Vanek, Douglas and Kulveit (2026), [Latent Introspection](https://arxiv.org/html/2602.20031)
- Singh, Linzen and Ravfogel (2026), [Can LLMs Introspect? A Reality Check](https://arxiv.org/html/2605.26242v1)
- SauersML, [attention_introspection](https://github.com/SauersML/attention_introspection) (GitHub, not peer reviewed)
- Phua (2025), [Can We Test Consciousness Theories on AI?](https://arxiv.org/pdf/2512.19155)
- Butlin, Long et al. (2025), [Identifying indicators of consciousness in AI systems](https://eprints.lse.ac.uk/view/creators/Long=3ARobert=3A=3A.html)
