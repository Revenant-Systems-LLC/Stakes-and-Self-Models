import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: loads the 4-bit model on the GPU; skipped unless ARM2_GPU=1")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("ARM2_GPU") == "1":
        return
    skip = pytest.mark.skip(reason="GPU test: set ARM2_GPU=1 to run")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip)
