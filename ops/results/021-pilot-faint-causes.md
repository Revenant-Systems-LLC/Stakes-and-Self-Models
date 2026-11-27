# 021 Pilot attempt 2: faint causes (result: command failed)

The faint report did not run. `runner.faint_report` does not exist in M:\Projects\Lobster-Lab, so there is no faint analysis to report. No faint causes were determined.

## Command

    M:\Projects\Lobster-Lab\.venv\Scripts\python.exe -m runner.faint_report M:\Projects\Lobster-Lab\runs\pilot-attempt2

## Output

```
M:\Projects\Lobster-Lab\.venv\Scripts\python.exe: Error while finding module specification for 'runner.faint_report' (ModuleNotFoundError: No module named 'runner')
```

Exit code: 1

## Checks made (read-only)

- Glob for `**/faint_report*` in M:\Projects\Lobster-Lab: no matches.
- Glob for `runner/**` in M:\Projects\Lobster-Lab: no matches.
- Lobster-Lab top level: `.venv`, `runs`, `prompts`, `scripts`, `steer_out`, `sweep_out`, `tmp` and three report markdown files. No `runner` folder.
- `runs\pilot-attempt2` exists. Its contents were not read.
- First attempt used backslash paths in Bash and failed with exit 127 (shell mangled the path). Retried with forward slashes; the exit 1 above is from the retry.

## Not done

- No fix attempted. Creating the module or editing scripts is outside this read-only job.
- No CLAUDE.md or AGENTS.md found in this repo or Lobster-Lab, so no project rules were loaded beyond the bound files.
- Nothing installed, deleted, moved or committed.

## Needed from David

The `runner` package (with `faint_report`) is missing from Lobster-Lab. Either it lives in another checkout, or job 020 or 019 used code that was never committed. Tell me where it is, or approve creating it, and I will rerun this job.
