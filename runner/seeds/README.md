Generator seed: 20261127

Rebuild or verify the seed lists (from the repository root, standard library only, written and tested on Python 3.12):

    python runner/seeds/make_seeds.py --check

Making them from scratch, when the four files do not exist yet:

    python runner/seeds/make_seeds.py

The command refuses to overwrite a file that exists. `--check` compares the files on disk with what the generator makes and exits 1 if they differ.

## What is in the folder

| File | Seeds | Used by |
|---|---:|---|
| dev.txt | 20 | dev runs on the fake client only (990000 to 990019; the dev range is 990000 to 990199) |
| pilot.txt | 40 | the pilot |
| confirmatory.txt | 1300 | the confirmatory phase: 400 pairs on each of three tiers, plus replacements for excluded pairs under the Exclusions rule in PREREGISTRATION.md |
| reserve.txt | 200 | the reserve phase (its cap is 0 now; the list stays) |
| tiers.txt | 150 | the exploratory Fable/Mythos phase: 120 for pairs plus 30 replacements |

## How they are made

The generator walks candidate numbers i = 0, 1, 2, ... and takes the first 8 bytes of `sha256("20261127:<i>")` modulo the range 1,000,000 to 99,999,999. A candidate that repeats, or that is in dev.txt, is skipped. The accepted numbers form one stream, and the files are cut from it in order: pilot, confirmatory, reserve, tiers. That is why no seed repeats within a file or across files. The range starts above the dev range, so a real seed can never fall in 990000 to 990199.

`runner/tests/test_seeds.py` checks all of this on every test run.

A seed list is fixed before any run. Do not edit these files after a run has started.
