"""The spend gate and the preflight.

No real API call unless STAKES_ALLOW_API is exactly "yes" in this process.
The API key is read by the anthropic SDK from ANTHROPIC_API_KEY in this
process's environment when the client is built; this module only checks that
the variable is non-empty and never keeps, prints or logs its value. The key
is never a user or system environment variable: the job watcher decrypts it
from the DPAPI store and sets it only for the one process it starts for an
approved API job.
"""

from __future__ import annotations

import importlib
import os

ENV_ALLOW = "STAKES_ALLOW_API"
ENV_KEY = "ANTHROPIC_API_KEY"


class ApiNotAllowed(RuntimeError):
    pass


class PreflightError(RuntimeError):
    pass


def api_allowed() -> bool:
    return os.environ.get(ENV_ALLOW) == "yes"


def mode_line() -> str:
    if api_allowed():
        return f"MODE: real API calls ENABLED ({ENV_ALLOW}=yes in this process). Spend is capped by the ledger."
    return f"MODE: fake client only ({ENV_ALLOW} is not exactly 'yes' in this process). No API calls can be made."


def preflight() -> None:
    """Run when the gate is open, before any episode, ledger write or log file.
    Raises PreflightError naming every failed check and how to fix it."""
    problems = []
    key = os.environ.get(ENV_KEY)
    if key is None or not key.strip():
        problems.append(
            f"{ENV_KEY} is not set (or is empty) in this process. For an approved API job the job watcher decrypts "
            f"it from your DPAPI store and sets it for the one process it starts. Run the job through the watcher. "
            f"Do not set it as a user or system environment variable.")
    try:
        importlib.import_module("anthropic")
    except Exception as e:  # ImportError, or a broken install failing while importing
        problems.append(
            f"the anthropic package does not import in this Python ({type(e).__name__}). It is installed in "
            f"M:\\Projects\\Lobster-Lab\\.venv when that venv is used; run the job with that interpreter, or ask "
            f"David before installing it anywhere.")
    if problems:
        raise PreflightError("\n".join(problems))


def make_claude_client():
    """The only place a real client is built. Refuses unless the gate is open and preflight passes.
    max_retries=0: the critter does its own counted backoff, so the SDK must not retry underneath it."""
    if not api_allowed():
        raise ApiNotAllowed(f"refusing to build a real API client: {ENV_ALLOW} is not exactly 'yes' in this process")
    preflight()
    import anthropic

    return anthropic.Anthropic(max_retries=0)
