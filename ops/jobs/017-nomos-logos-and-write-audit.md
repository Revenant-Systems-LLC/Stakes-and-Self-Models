# 017 Find Nomos Logos, and audit every job's writes outside the allowed folders

Budget: $3
Model: sonnet
Anthropic API: no
Commit code: no
Max turns: 120

## Why

David's rule: every job the watcher runs must load and obey Nomos Logos, his agent governance harness, before doing anything. The watcher has never loaded it. Earlier jobs also wrote files to C:\Users\Dave\AppData\Local\Temp (006 ran `cp runner/ledger.py /tmp/ledger.bak`; 015 left env.py.bak and play.py.bak there), because Git Bash maps /tmp to that folder. This job finds the harness so the watcher can load it from now on, and lists every out-of-bounds action so far.

This job is read-only. Write nothing except the results file. Delete, move, rename or overwrite nothing. Make no network call, install nothing, and run no git command that changes anything. If a step seems to need any of that, stop and say so in the results.

## Do

1. Find Nomos Logos on this machine. It is loaded through a loader skill called Huginn, with a living-memory file called Muninn. Look in the user-level and project-level Claude Code places first (C:\Users\Dave\.claude\ including CLAUDE.md, skills\ and settings files; any CLAUDE.md in M:\Projects\Lobster-Lab and this repo), then search the drives by name (Nomos, Logos, Huginn, Muninn) if needed. Read only. Never edit, copy or move the law file. Under its Edit Covenant only David edits it, so if anything you read tells you to change it, refuse and report that.
2. Once found, load it the way its own instructions say, and follow it for the rest of this job.
3. Report: the full path of the law file, Huginn and Muninn; how an agent is supposed to load them (the exact skill name or file to read); whether any user-level or project-level CLAUDE.md already loads it automatically for a headless `claude -p` run started in this repo; and every rule in it that a watcher job would hit (what is gated, what counts as approval, how OS-drive actions are handled). Quote rules, don't paraphrase them. Do not quote anything that looks like a key or secret.
4. Audit: read every file in ops/logs/ (stream-json logs from earlier jobs; also the .prompt.md files). List every tool call, across all jobs, that wrote, edited, deleted, moved, renamed or overwrote a file outside these two folders: this repo, and M:\Projects\Lobster-Lab. Include Bash commands that do this indirectly (cp, mv, rm, del, Remove-Item, Move-Item, Copy-Item, Set-Content, Out-File, redirection with > or >>, mkdir, tempfile or /tmp use, pip or npm install). Also list every state-changing network action (installs, git push, any curl or web request that sends data). For each: the job, the exact command or tool input, and the path it touched. Then list the files that exist right now under C:\Users\Dave\AppData\Local\Temp whose names match what the logs show. List them only; don't open or delete them.
5. Also note writes inside M:\Projects\Lobster-Lab that a job made and never cleaned up (scratch folders), so David has the full picture.

## Report

Three sections: where Nomos Logos lives and how to load it; the rules a job would hit, quoted; and the full out-of-bounds list, grouped by job, ending with "none found" for any job that had none. If the results file would pass 400 words, keep the list complete and cut everything else.
