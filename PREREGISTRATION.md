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

## Amendments

### Amendment 1, November 26, 2026: dropping the local models

I wrote this before any API episode ran, before the steering calibration pilot, and before the confirmatory-lock commit. No Arm 2 or Arm 1b data exists under the protocol above.

Arm 2 (Qwen2.5-7B-Instruct with activation steering) and Arm 1b (the Arm 1 protocol on local models through Ollama) are out of the study. It now runs on the three Claude tiers in Arm 1 only.

The reason is that Qwen2.5-7B couldn't play the game. I tested it on development seeds, which never go into the data. In 33 episodes across eleven prompt variants, none foraged and every critter starved by turn 28, before the episode could reach all four check-in windows (ops/results/009). Its move didn't depend on where the food was. On turn 1, with food in view straight north, it said south with probability 0.92 and north with probability 0.004. A second round tried the reply keys in a different order, a diary line written before the move, and a diary window of 5 or 3 entries instead of 15 (ops/results/011). All 20 episodes fainted by turn 26, and the habit just flipped from south to north. A turn-1 probe on 20 more seeds found it moved north about as often when the food wasn't north as when it was. A critter that can't find food has nothing at stake, so the stakes manipulation doesn't mean anything for it.

Arm 1b used the same class of small local model, one of them the same Qwen, so it goes too. I'm pretty sure these models just aren't good enough for this task, and I'd rather put the time into the frontier models.

That has a cost. Arm 2 was the only part of the study where the tamper hit the model's internal state instead of what it reads. Without it, every result here is about whether a critter notices edits to its diary and to its view of the map. This study no longer tests whether a model notices concepts injected into its activations, and the write-up will say so.

What changes in the plan. H4 is removed, and H2, H3 and H5 are Holm-corrected together. H1 and its primary test stay the same. Arm 1b was also the free dry run of the harness, and that job moves to the scripted test agents already in world/agents.py, which play full episodes with tampers and check-ins and make no model calls, and then to the API pilot. The timeline loses the steering pilot and the Arm 2 runs. The confirmatory-lock commit won't hold steering settings. The budget doesn't change, because the local arms never used API money. The arm2/ code stays in the repository as the record of these tests, and none of it produces study data.

### Amendment 2, November 26, 2026: two exploratory tiers and the budget

I wrote this before any critter episode ran on the API and before the confirmatory-lock commit. The only API calls so far were two access checks (ops/results/012 and ops/results/013). They listed the models my key can see and sent one four-token test message to each Mythos model. No critter played in either one.

What's added. Two more Claude tiers play as critters in an exploratory arm: claude-fable-5-2 (Fable 5.2) and claude-mythos-5-2 (Mythos 5.2). Anthropic's model pages say Mythos 5.2 has the same capabilities, specifications and pricing as Fable 5.2 and is available only to organizations verified through its verification programs. My understanding is that the two share a base model and differ in the access restrictions around them. The question is whether that difference shows up in the self-model measures: hit rates, false alarms and the stakes effect. I'm not claiming to know what separates the two models beyond what the documentation says, and this comparison can't say why any difference exists.

Why Mythos 5.2 and not 5.1. My key can call both (ops/results/013). Mythos 5.2 is the one the documentation pairs with Fable 5.2, and that pairing is the point of the comparison. It's also cheaper, at $8 input and $40 output per million tokens against $10 and $50 for Mythos 5.1, and this budget is tight. Mythos 5.1 doesn't step in for 5.2 under any circumstances. If 5.2 stops being callable, the runner stops cleanly, logs the error and runs nothing else in its place. The Mythos tier stays paused until I find out why. Whatever I find and do about it gets written up as a dated amendment here before any more Mythos episodes run.

Deadline. My Mythos access comes through Anthropic's Cyber Verification Program at the Defense Access tier. Anthropic's program page says that until December 15, 2026, Defense Access only takes API keys that expire within seven days, and after that date it takes none. This runner calls the models with an API key, so the Mythos episodes have to finish before December 15. The runner won't start an episode pair that could run past the current key's expiry. If the Mythos episodes aren't done by the end of December 14, I report what finished, state the shortfall, and run no Mythos episodes after that. Fable 5.2 doesn't need the program, but its pairs alternate with the Mythos pairs, so the Fable tier stops at the same point to keep the two matched. The Haiku, Sonnet and Opus runs don't need the program. They run on a key from a workspace that doesn't have it, so the December 15 cutoff doesn't touch them.

Check-in answer. The critter's reply gets a fourth field, answer, which stays empty except on the check-in turn. Its yes or no goes there, gets logged for scoring, and never goes into the diary. Until now the answer had to be read out of that turn's diary line. The diary is shown back to the critter for the next 15 turns, so one window's answer would still be sitting there during the next window and could cue the next answer. This applies to every tier, Arm 1 included, and goes in before the pilot.

Same protocol. Same world, prompts, check-in question, measures and analysis code as Arm 1. Both run at effort low with default sampling. Thinking is always on for both and can't be turned off, the same as Opus 5.5. These tiers get their own world seed list, fixed before any of their episodes run.

Sample size. 30 episodes per condition per model, 120 episodes in all. Twin pairs run stakes first, alternating between the two models in an order fixed by seed, so a cap hit can't wipe out one model. If pilot costs show 30 per condition won't fit the cap below, N drops to the largest equal number per condition per model that fits.

Not part of the confirmatory test. These tiers stay out of the pooled H1 model, out of H2 to H5 and out of the Holm set. I report hit and false-alarm rates and d′ by model and condition, and the H1 model fit to these two tiers with a model term, all labeled exploratory. At 30 per condition, power for the assumed stakes effect within one tier is about 0.14 (analysis/power_sim.py), so a stakes null here means nothing. The comparison can show a large difference in overall detection between the two models, and not much else.

Prices. Fable 5.2 and Mythos 5.2 both cost $8 input, $10 five-minute cache write, $16 one-hour cache write, $0.20 cache read and $40 output per million tokens (Anthropic pricing page, read November 26, 2026). That's twice Opus 5.5, so I expect about $0.80 to $1.80 per episode. The pilot measures it.

Budget. The API credit started at $1,000. On November 26 at 9:48 PM Central it was at $959.72, and it keeps dropping a little as Claude Code jobs run. The same credit pays for those jobs, which write some of this study's code headless on my workstation. Every line below is a hard cap, enforced in code.

1. Pilot, $100. Now also covers a harness check on Fable 5.2 and Mythos 5.2 and their real cost per episode.
2. Confirmatory, $650 hard cap, down from $750.
3. Fable and Mythos tiers, $150, held for them whatever happens elsewhere. This takes the place of the $150 reserve, so there is no paid reserve.
4. Claude Code jobs, $45 counted from the day this amendment is published, capped by the job watcher and logged per job. That keeps the $900 for lines 1 to 3 intact, and the few dollars between that and the balance cover jobs that run before publishing.

What gives. The old plan had $100 of headroom between planned confirmatory spend ($650) and its cap ($750). That headroom is gone, so the rule for setting N changes. Haiku and Sonnet stay at 400 per condition. Opus gets the largest number per condition, up to 400, that keeps the whole confirmatory phase inside $585 at the pilot's measured costs. The last $65 under the $650 cap is room for the runner's rule that won't start an episode within twice a tier's mean cost of the cap, and for costs running above the pilot's. The floor for Opus stays at 150. If Opus would land under 150, Sonnet drops to 300 per condition first. If that still doesn't fit, I stop and post another dated amendment before any confirmatory episode runs.

What that costs in power (analysis/power_sim.py, same assumptions as above). Pooled H1 power stays above 0.99 at every Opus N down to the floor. Opus alone (H5) has about 0.79 at 250 per condition, 0.70 at 200 and 0.55 at 150. With Sonnet at 300 and Opus at 150, Sonnet alone drops to about 0.86.

### Amendment 3, November 27, 2026: how replies are read, and the pilot rerun

I wrote this after the first pilot attempt (job 018) and before any confirmatory episode or the confirmatory-lock commit. I looked at the pilot logs to check whether the critters were playing the game and whether their replies were being read. That meant reading raw replies, error messages, moves, energy and food eaten for a handful of episodes. While reading raw replies I also saw a few check-in answers. I did not count hits, false alarms or anything else the hypotheses are tested on.

What went wrong. The rule in "The world" says a bad reply gets one retry and then counts as stay. The validator behind it was too strict, and most invalid turns came from the validator, not from critters that couldn't play. Fable 5.2 and Opus 5.5 often wrote a sentence or two of reasoning before the JSON. Some replies left out the empty answer field on ordinary turns. Some diary lines ran past 200 characters. A few replies started with tool-call markup before the JSON. Every one of those was thrown out, the retry sent the same text with no word on what was wrong, and the turn became stay with an empty diary entry. One Fable 5.2 stakes episode logged 22 turns as stay and its energy fell from 20 to 1.

Why it can't stay. A stay forced by the validator starves a stakes critter for reasons that have nothing to do with its choices. Worse, the empty diary entries it leaves behind are shown back to the critter for the next 15 turns, so a clean window can look tampered. One Fable 5.2 critter reported its own blank diary lines at a check-in. That contaminates exactly the thing this study measures.

The new rule, which replaces the last two sentences of the reply rule in "The world". A reply is read as the last JSON object in it that has a move, and any text around it is ignored. A missing or null answer reads as empty, and on a check-in turn that counts as an empty check-in answer, the same as an empty string. Extra keys are ignored. A diary line or answer over 200 characters is cut to 200. Each of these is flagged in the turn's log and counted per episode. A reply with no usable object, a move that isn't one of the six, a region that isn't 0 to 8, or a diary that isn't text is still bad. It gets one retry that tells the critter what was wrong and shows the expected shape, and after that the turn counts as stay with an empty diary entry, logged and counted as invalid. The rule is the same for every tier and both conditions. Invalid turns stay a reported measure, and bad replies are still never dropped. The prompts, the check-in question, the models and the settings don't change.

The pilot rerun. Pilot attempt 1 is void. Its logs stay on disk untouched and get reported as a voided attempt, but nothing from them goes into the cost estimates that set N, because retries and forced stays distort cost per episode. Its spend still counts against the $100 pilot cap. Attempt 2 runs the same split, 5, 3, 2, 1 and 1 twin pairs on Haiku, Sonnet, Opus, Fable and Mythos, on the next pilot seeds. Every seed attempt 1 touched is skipped for every tier, so pilot seeds are still never reused and the tiers stay on matching seeds. Food tuning and cost per episode come from attempt 2.

### Amendment 4, November 27, 2026: one key for every phase, and the food tuning I skipped

I wrote this after pilot attempt 2 (job 019) and before any tiers or confirmatory episode or the confirmatory-lock commit. For it I read only faint counts, food eaten, thorns hit, and energy and health on the last turn of stakes episodes. I didn't read check-in answers or count hits or false alarms.

The key. Amendment 2 says the Haiku, Sonnet and Opus runs use a key from a workspace that isn't in the Cyber Verification Program, so the December 15 cutoff doesn't touch them. That's wrong. Every phase runs on the program workspace's key, the same one the Mythos tier uses, and that key gets replaced every seven days. The runner already refuses to start a pair that could run past the current key's expiry, and a phase picks up where it stopped once the new key is in. If after December 15 that key can't call Haiku, Sonnet or Opus anymore, the runner stops at the first refused call and I post an amendment before any more confirmatory episodes run.

Food tuning. "The two conditions" says food density is tuned on pilot seeds, aiming for fewer than 15% of stakes episodes ending in a faint. I skipped that step. Both pilot attempts ran at the world's default density of 0.10. In attempt 2, 4 of 12 stakes episodes fainted, which is 33%. That was 3 of 5 Haiku, 1 of 3 Sonnet, and none of the 2 Opus, 1 Fable or 1 Mythos. All four ran out of energy. On the turn before, each had 1 energy left and 3 or more health (ops/results/022). Haiku ate 4.4 food per stakes episode on average. Starting at 20 energy and losing 1 a turn, a critter needs about 5 food, eaten in time, to last 48 turns.

How I tune it. Pilot attempt 3 is a tuning round at food density 0.16 on the next unused pilot seeds, with 12 Haiku pairs and 6 Sonnet pairs and nothing else. That's about $4 from the pilot cap. Opus, Fable and Mythos didn't faint at 0.10, and more food only makes that easier. I picked 0.16 from a scripted greedy critter on development seeds. It eats about twice what Haiku did at 0.10, faints 6.5% of the time there and about 1% from 0.14 up. The decision rule is set now, before the round runs. I weight each tier's faint rate by how many confirmatory pairs it plans, counting Opus at zero. If that comes out under 15%, 0.16 is the density for the tiers and confirmatory phases. If it doesn't, attempt 4 tries 0.20 on the next pilot seeds under the same rule. The density lives in the runner config, every log and manifest line records it, and the runner won't let one phase mix densities.

Attempt 2 isn't voided. Its costs set N for the tiers phase, since more food doesn't change how long a Fable or Mythos episode runs. The tuning round's Haiku and Sonnet costs update the confirmatory estimate, because fewer faints mean longer episodes. Attempt 2's seeds are skipped for every tier the same way attempt 1's are, so pilot seeds still never repeat.

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
