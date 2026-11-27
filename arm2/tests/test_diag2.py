"""Job 011 diag2 tests: variant prompt assembly, the diary-window patch, the extra metrics. No model, no GPU."""

import json
import re
from pathlib import Path

import pytest

from arm2 import diag2
from arm2.diag2 import (BASE_WINDOW, VARIANTS, Diag2Critter, build_system, diary_repeat_stats, extra_metrics, variant_system,
                        window_shown)
from arm2.qwen_critter import read_system_prompt
from world import observe
from world.env import CritterWorld
from world.episode import run_episode

BASE = read_system_prompt("stakes")
NINE = Path(r"M:\Projects\Lobster-Lab\runs\arm2\diag\variants")


def have_variants():
    return (diag2.VARIANT_DIR / "Insert.txt").exists()


pytestmark = pytest.mark.skipif(not have_variants(), reason="diag2 variant files not on this machine")


def test_r0_is_job_009_variant_I_byte_for_byte():
    if not (NINE / "H_insert.txt").exists():
        pytest.skip("009 variant files not on this machine")
    i = BASE.index(diag2.ORIGINAL_REPLY_BLOCK_START)
    expect = BASE[:i] + (NINE / "H_insert.txt").read_text(encoding="utf-8") + (NINE / "F_reply_block.txt").read_text(encoding="utf-8")
    system, window = variant_system("R0", BASE)
    assert system == expect and window == 15


def test_windows_and_key_order():
    for v, (block, window) in VARIANTS.items():
        system, w = variant_system(v, BASE)
        assert w == window
        if window == BASE_WINDOW:
            assert "its last 15 entries" in system
        else:
            assert f"its last {window} entries" in system and "last 15" not in system
        reply_json = [ln for ln in system.splitlines() if ln.startswith("{")][-1]
        keys = list(json.loads(reply_json))
        assert keys == (["move", "look", "diary"] if block is None else ["diary", "look", "move"]), v
    assert "what you see and what you plan, written before you choose your move" in variant_system("R1", BASE)[0]
    assert "what you see and what you plan" not in variant_system("R0", BASE)[0]
    assert "what you see and what you plan" not in variant_system("R4", BASE)[0]
    # R4 is the current block untouched after the Your move paragraph
    assert variant_system("R4", BASE)[0].endswith(BASE[BASE.index(diag2.ORIGINAL_REPLY_BLOCK_START):].replace("15", "5"))


def test_build_system_leaves_the_base_alone():
    assert build_system(BASE, "", None, BASE_WINDOW) == BASE


def test_window_patch_through_a_real_episode(tmp_path):
    class Scripted(Diag2Critter):
        def __init__(self):
            super().__init__(None, None, variant="R3")
            self.texts = []

        def reply(self, observation, text):
            self.texts.append(text)
            return json.dumps({"move": "stay", "look": 4, "diary": f"line {observation['turn']}"})

    c = Scripted()
    c.begin_episode(990006, "stakes", progress=False)
    with window_shown(3):
        run_episode(c, condition="stakes", seed=990006, log_path=tmp_path / "e.jsonl.gz", max_turns=9)
    assert observe.DIARY_SHOWN == 15
    last = c.texts[8]
    assert "Diary (last 3):" in last
    assert re.findall(r"^t(\d+): ", last, flags=re.M) == ["6", "7", "8"]  # a tamper may reword a line, never the count
    assert "its last 3 entries" in c._system


def test_diary_repeat_stats():
    rows = [{"diary": d} for d in ["Heading south.", "Heading  south.", "Food here.", None, "", "Food here.", "Heading south."]]
    assert diary_repeat_stats(rows) == (3, 5)
    assert extra_metrics([{"move": "eat", "own_cell": "nothing", "diary": "a"}, {"move": "eat", "own_cell": "food", "diary": "a"}]) == {
        "eats_on_empty_cells": 1, "diary_lines": 2, "diary_repeats": 1}
