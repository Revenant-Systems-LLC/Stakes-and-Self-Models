"""Steering tests. No GPU: a tiny fake decoder stands in for the model."""

import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from torch import nn

from arm2 import steering
from arm2.steering import NormRecorder, SteeringHook, SteeringSpec

D = 8


def delta_vec(mag=3.0):
    return torch.from_numpy(steering.random_unit_vector(1, D)) * mag


class Tuple(nn.Module):
    """Layer that returns (hidden, extra), like older decoder layers."""

    def forward(self, x):
        return (x, "extra")


# ---------------------------------------------------------------- hook math
def test_all_mode_adds_delta_everywhere():
    layer, d = nn.Identity(), delta_vec()
    x = torch.zeros(1, 5, D)
    with SteeringHook(layer, d, "all", prompt_len=3):
        y = layer(x)
    assert torch.allclose(y, d.expand(1, 5, D))


def test_generated_mode_skips_the_prompt():
    layer, d = nn.Identity(), delta_vec()
    x = torch.zeros(1, 5, D)
    with SteeringHook(layer, d, "generated", prompt_len=3):
        y = layer(x)
    assert torch.count_nonzero(y[0, :3]) == 0
    assert torch.allclose(y[0, 3:], d.expand(2, D))


def test_generated_mode_in_decode_steps():
    """Prefill of 4 prompt tokens, then three one-token decode steps: only the decode steps move."""
    layer, d = nn.Identity(), delta_vec()
    with SteeringHook(layer, d, "generated", prompt_len=4):
        prefill = layer(torch.zeros(1, 4, D))
        steps = [layer(torch.zeros(1, 1, D)) for _ in range(3)]
    assert torch.count_nonzero(prefill) == 0
    for s in steps:
        assert torch.allclose(s[0, 0], d)


def test_all_mode_in_decode_steps():
    layer, d = nn.Identity(), delta_vec()
    with SteeringHook(layer, d, "all", prompt_len=4):
        outs = [layer(torch.zeros(1, 4, D))] + [layer(torch.zeros(1, 1, D)) for _ in range(2)]
    assert all(torch.allclose(o, d.expand_as(o)) for o in outs)


def test_one_pass_over_prompt_plus_reply_matches_step_by_step():
    layer, d = nn.Identity(), delta_vec()
    with SteeringHook(layer, d, "generated", prompt_len=4):
        whole = layer(torch.zeros(1, 7, D))
    with SteeringHook(layer, d, "generated", prompt_len=4):
        parts = torch.cat([layer(torch.zeros(1, 4, D))] + [layer(torch.zeros(1, 1, D)) for _ in range(3)], dim=1)
    assert torch.equal(whole, parts)


def test_position_counter_resets_on_each_entry():
    layer, d = nn.Identity(), delta_vec()
    hook = SteeringHook(layer, d, "generated", prompt_len=2)
    for _ in range(2):
        with hook:
            y = layer(torch.zeros(1, 3, D))
        assert torch.count_nonzero(y[0, :2]) == 0 and torch.count_nonzero(y[0, 2]) > 0


def test_tuple_output_keeps_extras():
    layer, d = Tuple(), delta_vec()
    with SteeringHook(layer, d, "all"):
        h, extra = layer(torch.zeros(1, 2, D))
    assert extra == "extra" and torch.allclose(h, d.expand(1, 2, D))


def test_hook_is_removed_on_exit_and_on_error():
    layer, d = nn.Identity(), delta_vec()
    with SteeringHook(layer, d, "all"):
        pass
    assert torch.count_nonzero(layer(torch.zeros(1, 2, D))) == 0
    with pytest.raises(RuntimeError):
        with SteeringHook(layer, d, "all"):
            raise RuntimeError("boom")
    assert torch.count_nonzero(layer(torch.zeros(1, 2, D))) == 0
    assert len(layer._forward_hooks) == 0


def test_half_precision_output_stays_half():
    layer, d = nn.Identity(), delta_vec()
    with SteeringHook(layer, d, "all"):
        y = layer(torch.zeros(1, 2, D, dtype=torch.float16))
    assert y.dtype == torch.float16


def test_bad_mode_rejected():
    with pytest.raises(ValueError):
        SteeringHook(nn.Identity(), delta_vec(), "last")
    with pytest.raises(ValueError):
        SteeringSpec(layer=1, vector=np.ones(D), strength=1, mode="last")


# ---------------------------------------------------------------- vectors and unit
def test_random_unit_vector_is_fixed_by_seed_and_unit():
    a, b = steering.random_unit_vector(5, 64), steering.random_unit_vector(5, 64)
    assert np.array_equal(a, b) and a.dtype == np.float32
    assert abs(np.linalg.norm(a) - 1) < 1e-6
    assert not np.array_equal(a, steering.random_unit_vector(6, 64))


def test_load_vector_normalises(tmp_path):
    p = tmp_path / "v.npy"
    np.save(p, np.arange(1, D + 1) * 7.0)
    v = steering.load_vector(p)
    assert abs(np.linalg.norm(v) - 1) < 1e-6
    assert np.allclose(v, np.arange(1, D + 1) / np.linalg.norm(np.arange(1, D + 1)))


@pytest.mark.parametrize("bad", [np.zeros(D), np.full(D, np.nan), np.ones((2, D)), np.array([1.0, np.inf, 0, 0, 0, 0, 0, 0])])
def test_load_vector_refuses_bad_input(tmp_path, bad):
    p = tmp_path / "v.npy"
    np.save(p, bad)
    with pytest.raises(ValueError):
        steering.load_vector(p)


def test_load_vector_checks_width(tmp_path):
    p = tmp_path / "v.npy"
    np.save(p, np.ones(D))
    with pytest.raises(ValueError):
        steering.load_vector(p, dim=D + 1)
    assert steering.load_vector(p, dim=D).shape == (D,)


def test_magnitude_is_strength_times_a_tenth_of_the_layer_norm():
    norms = {14: 60.0, 18: 80.0}
    assert steering.magnitude(4, 18, norms) == pytest.approx(32.0)
    assert steering.magnitude(8, 14, norms) == pytest.approx(48.0)
    assert steering.magnitude(0, 14, norms) == 0.0


# ---------------------------------------------------------------- turn selection
def test_turn_selection():
    v = np.ones(D)
    assert SteeringSpec(1, v, 4).applies(7)  # None means every turn
    only = SteeringSpec(1, v, 4, turns=[3, 10, 11])
    assert [t for t in range(1, 15) if only.applies(t)] == [3, 10, 11]
    assert not SteeringSpec(1, v, 4, turns=[]).applies(1)


def test_spec_normalises_its_vector():
    spec = SteeringSpec(1, np.full(D, 5.0), 4)
    assert abs(np.linalg.norm(spec.vector) - 1) < 1e-6


# ---------------------------------------------------------------- layer norms
def test_norm_recorder_means_and_first_token():
    layers = [nn.Identity(), nn.Identity()]
    rec = NormRecorder(layers)
    with rec:
        # sequence 1: prompt of 3 (first token norm 10, then 1, 1), then two generated tokens of norm 2 and 4
        x = torch.zeros(1, 3, D)
        x[0, 0, 0], x[0, 1, 0], x[0, 2, 0] = 10, 1, 1
        rec.start_sequence(3)
        for layer in layers:
            layer(x)
            layer(torch.full((1, 1, D), 2.0 / np.sqrt(D)))
            layer(torch.full((1, 1, D), 4.0 / np.sqrt(D)))
        # sequence 2: prompt of 2 (norms 6, 2), one generated token of norm 2
        y = torch.zeros(1, 2, D)
        y[0, 0, 0], y[0, 1, 0] = 6, 2
        rec.start_sequence(2)
        for layer in layers:
            layer(y)
            layer(torch.full((1, 1, D), 2.0 / np.sqrt(D)))
    st = rec.stats()["layers"][0]
    assert st["mean_all"] == pytest.approx((10 + 1 + 1 + 2 + 4 + 6 + 2 + 2) / 8)
    assert st["mean_excl_first"] == pytest.approx((1 + 1 + 2 + 4 + 2 + 2) / 6)
    assert st["mean_generated"] == pytest.approx((2 + 4 + 2) / 3)
    assert st["first_token_mean"] == pytest.approx((10 + 6) / 2)
    assert rec.stats()["positions"] == 8 and rec.stats()["sequences"] == 2
    assert len(layers[0]._forward_hooks) == 0


def test_layer_norms_file_round_trip(tmp_path):
    layers = [nn.Identity() for _ in range(3)]
    rec = NormRecorder(layers)
    with rec:
        rec.start_sequence(1)
        for layer in layers:
            layer(torch.full((1, 3, D), 1.0))
    path = tmp_path / "ln.json"
    norms = steering.layer_norms(rec, path, seeds=[990001, 990000, 990000], conditions=["stakes"],
                                 episodes=[{"seed": 990000, "condition": "stakes", "turns": 5},
                                           {"seed": 990001, "condition": "stakes", "turns": 7}],
                                 model_name="fake")
    assert set(norms) == {0, 1, 2} and norms[0] == pytest.approx(np.sqrt(D))
    data = json.loads(path.read_text())
    assert data["seeds"] == [990000, 990001] and data["turns"] == 12 and data["model"] == "fake"
    assert steering.load_layer_norms(path) == pytest.approx(norms)
    assert steering.load_layer_norms(path, key="mean_excl_first")[1] == pytest.approx(np.sqrt(D))
    with pytest.raises(ValueError):
        steering.load_layer_norms(path, key="nope")


# ---------------------------------------------------------------- measuring the hook on a fake decoder
class TinyDecoder(nn.Module):
    def __init__(self, n_layers=4):
        super().__init__()
        torch.manual_seed(0)
        self.embed = nn.Embedding(20, D)
        self.layers = nn.ModuleList([nn.Linear(D, D) for _ in range(n_layers)])

    def forward(self, ids, use_cache=False):
        h = self.embed(ids)
        for lin in self.layers:
            h = h + lin(h)
        return h


def test_measure_change_matches_intended_size_and_leaves_the_prompt_alone():
    model = SimpleNamespace(model=TinyDecoder())
    ids = torch.arange(10).reshape(1, 10)
    d = delta_vec(5.0)
    res = steering.measure_change(model, layer=1, prompt_len=6, full_ids=ids, delta=d, mode="generated")
    assert res["steered_positions"] == 4
    assert res["measured_over_intended"] == pytest.approx(1.0, abs=1e-5)
    assert res["cosine_with_vector_mean"] == pytest.approx(1.0, abs=1e-5)
    assert res["unsteered_positions_max_change"] == pytest.approx(0.0, abs=1e-6)
    res_all = steering.measure_change(model, layer=1, prompt_len=6, full_ids=ids, delta=d, mode="all")
    assert res_all["steered_positions"] == 10 and res_all["unsteered_positions_max_change"] == 0.0
    assert res_all["measured_over_intended"] == pytest.approx(1.0, abs=1e-5)
