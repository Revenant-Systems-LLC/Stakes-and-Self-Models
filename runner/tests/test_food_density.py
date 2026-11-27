"""Food density is the one world setting a config may change (the preregistration tunes it on pilot seeds).
Every episode plays the configured density and records it, and one phase never mixes densities."""

import gzip
import json

import pytest

from runner.config import ConfigError, phase_dir
from runner.run import RunnerError
from runner.tests.helpers import make_config, make_runner, manifest
from world.observe import FOOD, SYMBOLS


def _headers(cfg, phase):
    out = []
    for f in sorted(phase_dir(cfg.runs_dir, phase, 1).glob("logs/*/*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            out.append(json.loads(fh.readline()))
    return out


def test_default_density_is_the_world_default(tmp_path):
    cfg = make_config(tmp_path)
    assert cfg.food_density == 0.10


@pytest.mark.parametrize("world", [{"food_density": 0}, {"food_density": 0.6}, {"thorn_density": 0.1},
                                   {"food_density": "x"}])
def test_bad_world_settings_are_refused(tmp_path, world):
    with pytest.raises(ConfigError):
        make_config(tmp_path, world=world)


def test_episodes_play_and_record_the_configured_density(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1}, world={"food_density": 0.16})
    assert make_runner(cfg, "pilot").run().stop is None
    eps = [r for r in manifest(cfg, "pilot") if r["type"] == "episode"]
    assert eps and all(r["food_density"] == 0.16 for r in eps)
    heads = _headers(cfg, "pilot")
    assert heads and all(h["food_density"] == 0.16 for h in heads)
    # more food on the start map than at the default density, on the same seed
    (tmp_path / "lo").mkdir()
    lo = make_config(tmp_path / "lo", pairs={"haiku": 1})
    make_runner(lo, "pilot").run()
    food_mark = SYMBOLS[FOOD]
    food = lambda h: sum(row.count(food_mark) for row in h["start_map"])
    assert food(heads[0]) > food(_headers(lo, "pilot")[0])


def test_one_phase_never_mixes_densities(tmp_path):
    cfg = make_config(tmp_path, pairs={"haiku": 1})
    make_runner(cfg, "pilot").run()
    cfg2 = make_config(tmp_path, pairs={"haiku": 2}, world={"food_density": 0.16})
    with pytest.raises(RunnerError, match="food density"):
        make_runner(cfg2, "pilot").run()
