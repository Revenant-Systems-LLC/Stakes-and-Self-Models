# 017 Find Nomos Logos, and audit every job's writes outside the allowed folders

Budget: $3
Model: sonnet
Anthropic API: no
Commit code: no
Max turns: 120

## Why

David's rule: every job the watcher runs must load and obey Nomos Logos, his agent governance harness, before doing anything. The watcher has never loaded it. Earlier jobs also wrote files to C:\Users\Dave\AppData\Local\Temp (006 ran `cp runner/ledger.py /tmp/ledger.bak`; 015 left env.py.bak and play.py.bak there), because Git Bash maps /tmp to that folder. From this job on, the watcher opens every job with the Nomos Logos boot order. This job confirms those files are where the machine index says, and lists every out-of-bounds action so far.

This job is read-only. Write nothing except the results file. Delete, move, rename or overwrite nothing. Make no network call, install nothing, and run no git command that changes anything. If a step seems to need any of that, stop and say so in the results.

## Do

1. The watcher has given you the Nomos Logos boot order above. Report whether each file in it exists at that path (read only), and whether any user-level or project-level CLAUDE.md or settings file already made a headless `claude -p` run in this repo load Nomos Logos before this change. Never edit, copy or move the law file. Under its Edit Covenant only David edits it.
2. Do not search the drives and do not walk M:\ai-armory. The paths are known.
3. List every rule in Nomos Logos and the machine index that a watcher job hits (what is gated, what counts as approval, how C: deletes are handled, git rules). Quote them, don't paraphrase. Do not quote anything that looks like a key or secret.
4. Audit: read every file in ops/logs/ (stream-json logs from earlier jobs; also the .prompt.md files). List every tool call, across all jobs, that wrote, edited, deleted, moved, renamed or overwrote a file outside these two folders: this repo, and M:\Projects\Lobster-Lab. Include Bash commands that do this indirectly (cp, mv, rm, del, Remove-Item, Move-Item, Copy-Item, Set-Content, Out-File, redirection with > or >>, mkdir, tempfile or /tmp use, pip or npm install). Also list every state-changing network action (installs, git push, any curl or web request that sends data). For each: the job, the exact command or tool input, and the path it touched. Then list the files that exist right now under C:\Users\Dave\AppData\Local\Temp whose names match what the logs show, plus the pytest-of-Dave folder that pytest's tmp_path uses by default. List them only; don't open or delete them.
5. Job 016 (scripted dry run) was stopped by hand partway through. From ops/logs/016-scripted-dry-run.log, report how far it got: each step it reached, every file it created, edited or deleted, and whether its step 5 ran, that is whether it deleted any of M:\Projects\Lobster-Lab\runs\_runner_test_tmp, _runner_demo_014 or _015_scratch. Then check whether those three folders exist right now (list only). Note any uncommitted changes it left in this repo (git status, read-only).
6. Also note writes inside M:\Projects\Lobster-Lab that a job made and never cleaned up (scratch folders), so David has the full picture.

## Report

Four sections: whether the boot files exist and whether anything loaded them before; the rules a job would hit, quoted; what job 016 did before it was stopped; and the full out-of-bounds list, grouped by job, ending with "none found" for any job that had none. If the results file would pass 400 words, keep the list complete and cut everything else.
