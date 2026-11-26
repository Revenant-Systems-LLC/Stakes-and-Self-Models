# Stakes and self-models

Does an AI critter that has to keep its own body alive get better at noticing when someone secretly tampers with its memory or its attention? This repo holds the experiment that tests it. Critters play a small foraging game. One group has energy and health that can end the game, and the other plays the same game for points with no body. Every few turns the game either edits the critter's diary, shows it a different part of the map than it chose to look at, or does nothing, and then asks whether anything didn't match. The measure is how much more often it says yes when something really changed.

The main arm runs Claude critters on Haiku, Sonnet and Opus through the Anthropic API. A second arm runs small open-weight models on my own GPU, where the tampering is activation steering.

Right now the repo holds PREREGISTRATION.md, with the hypotheses, design, controls, budget, sample size and analysis plan, and analysis/power_sim.py, the simulation behind the sample size. They were committed before any experiment code, so the commit date shows the plan came first. Code, logs and the replay viewer land here as they get built. Results and data go to Zenodo.

The claim is about how accurate a self-model is. It isn't a claim that any model is conscious or feels anything.

David Fisher, Revenant Systems LLC
