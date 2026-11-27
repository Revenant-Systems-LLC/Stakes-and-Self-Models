import os
import re
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Scratch space on M:. The built-in tmp_path lives on the system drive, which agents may not write to.
# Nothing here is ever deleted by the tests; the directories are small.
# STAKES_TEST_SCRATCH overrides it for test runs off Yggdrasil (a Linux checkout has no M:).
SCRATCH = Path(os.environ.get("STAKES_TEST_SCRATCH") or r"M:\Projects\Lobster-Lab\runs\_runner_test_tmp")


@pytest.fixture
def tmp_path(request):
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", request.node.name)[:40]
    p = SCRATCH / f"{name}-{uuid.uuid4().hex[:8]}"
    p.mkdir(parents=True)
    return p


class _Tripwire:
    def __init__(self, *a, **kw):
        raise AssertionError("a real anthropic client was constructed inside a test")


@pytest.fixture(autouse=True)
def _no_real_api(monkeypatch):
    """No test may open the spend gate by accident, hold a real key, or build a real client."""
    monkeypatch.delenv("STAKES_ALLOW_API", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        import anthropic
    except ImportError:
        return
    monkeypatch.setattr(anthropic, "Anthropic", _Tripwire)
