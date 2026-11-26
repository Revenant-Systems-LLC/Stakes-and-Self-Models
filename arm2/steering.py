"""Residual-stream steering for the Arm 2 critter.

Unit (PREREGISTRATION.md, Arm 2): strength s adds  s x 0.1 x N_L x v_hat  to the
output of decoder layer L, where N_L is that layer's average residual-stream
norm and v_hat is a unit vector. Strength 8 adds 0.8 of a typical residual.

N_L comes from layer_norms(): the mean L2 norm of model.model.layers[L]'s
output over token positions of unsteered critter turns on dev seeds. Three
averages are saved, because Qwen's first token is an attention sink with a
huge norm and the choice matters for the unit:
  mean_all        every position (prompt and generated). The default.
  mean_excl_first all positions except the first of each sequence.
  mean_generated  only positions the model generated.

Position modes: "generated" adds the vector only at positions at or after the
prompt length (tokens the model generates; the prompt is untouched), "all"
adds it at every position, prompt included.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

SCALE = 0.1
MODES = ("generated", "all")
NORM_KEYS = ("mean_all", "mean_excl_first", "mean_generated")
DEFAULT_NORM_KEY = "mean_all"
RUNS_DIR = Path(r"M:\Projects\Lobster-Lab\runs\arm2")
LAYER_NORMS_PATH = RUNS_DIR / "layer_norms.json"


# ---------------------------------------------------------------- vectors
def random_unit_vector(seed: int, dim: int) -> np.ndarray:
    """A fixed-seed random direction, unit length, float32."""
    v = np.random.default_rng(seed).standard_normal(dim)
    return (v / np.linalg.norm(v)).astype(np.float32)


def unit(vec, dim: int | None = None) -> np.ndarray:
    """Return vec as a 1-D float32 unit vector. Refuses NaN/inf, zero length, wrong size."""
    v = np.asarray(vec, dtype=np.float64)
    if v.ndim != 1:
        raise ValueError(f"steering vector must be 1-D, got shape {v.shape}")
    if dim is not None and v.shape[0] != dim:
        raise ValueError(f"steering vector has {v.shape[0]} entries, model width is {dim}")
    if not np.all(np.isfinite(v)):
        raise ValueError("steering vector has NaN or inf")
    n = np.linalg.norm(v)
    if n == 0:
        raise ValueError("steering vector has zero length")
    return (v / n).astype(np.float32)


def load_vector(path: str | Path, dim: int | None = None) -> np.ndarray:
    """Load a .npy vector and normalise it to unit length."""
    return unit(np.load(path, allow_pickle=False), dim)


def magnitude(strength: float, layer: int, norms: dict[int, float]) -> float:
    """Size of the added vector: strength x 0.1 x layer_norms[layer]."""
    return float(strength) * SCALE * float(norms[layer])


@dataclass
class SteeringSpec:
    """What to steer: one layer, one unit vector, one strength, which turns."""

    layer: int
    vector: np.ndarray  # unit length, set through unit()
    strength: float
    mode: str = "generated"
    turns: frozenset | None = None  # None = every turn

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}")
        self.vector = unit(self.vector)
        if self.turns is not None:
            self.turns = frozenset(int(t) for t in self.turns)

    def applies(self, turn: int) -> bool:
        return self.turns is None or int(turn) in self.turns


# ---------------------------------------------------------------- the hook
def _hidden(output):
    return output[0] if isinstance(output, tuple) else output


class SteeringHook:
    """Context-managed forward hook that adds `delta` to a layer's output.

    delta is the full added vector (magnitude already applied), shape (D,).
    Positions are counted across calls, so the prefill call (T = prompt length)
    and each one-token decode step see the right absolute position. Batch size 1.
    """

    def __init__(self, layer_module: torch.nn.Module, delta: torch.Tensor, mode: str = "generated",
                 prompt_len: int = 0):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self.layer_module = layer_module
        self.delta = delta.detach().float()
        self.mode = mode
        self.prompt_len = int(prompt_len)
        self._seen = 0
        self._handle = None

    def _hook(self, module, args, output):
        h = _hidden(output)
        t = h.shape[-2]
        if self.mode == "all":
            add = self.delta.expand(t, -1)
        else:
            pos = torch.arange(self._seen, self._seen + t, device=h.device)
            add = (pos >= self.prompt_len).unsqueeze(-1).float() * self.delta.to(h.device)
        self._seen += t
        new = h + add.to(device=h.device, dtype=h.dtype)
        return (new,) + tuple(output[1:]) if isinstance(output, tuple) else new

    def __enter__(self):
        self._seen = 0
        self.delta = self.delta.to(next(self.layer_module.parameters(), self.delta).device) \
            if any(True for _ in self.layer_module.parameters()) else self.delta
        self._handle = self.layer_module.register_forward_hook(self._hook)
        return self

    def __exit__(self, *exc):
        if self._handle is not None:
            self._handle.remove()
            self._handle = None
        return False


# ---------------------------------------------------------------- layer norms
class NormRecorder:
    """Accumulates residual-stream norms for every decoder layer, no GPU sync per step.

    Call start_sequence(prompt_len) before each generate() so the first token
    of each sequence and the generated positions can be told apart.
    """

    def __init__(self, layers):
        self.layers = list(layers)
        n = len(self.layers)
        self.sum_all = torch.zeros(n, dtype=torch.float64)
        self.n_all = torch.zeros(n, dtype=torch.float64)
        self.sum_first = torch.zeros(n, dtype=torch.float64)
        self.n_first = torch.zeros(n, dtype=torch.float64)
        self.sum_gen = torch.zeros(n, dtype=torch.float64)
        self.n_gen = torch.zeros(n, dtype=torch.float64)
        self._seen = [0] * n
        self._prompt_len = 0
        self._handles = []
        self.sequences = 0

    def start_sequence(self, prompt_len: int):
        self._seen = [0] * len(self.layers)
        self._prompt_len = int(prompt_len)
        self.sequences += 1

    def _make_hook(self, i):
        def hook(module, args, output):
            h = _hidden(output)
            if self.sum_all.device != h.device:
                for name in ("sum_all", "n_all", "sum_first", "n_first", "sum_gen", "n_gen"):
                    setattr(self, name, getattr(self, name).to(h.device))
            norms = h.detach().float().norm(dim=-1).reshape(-1)  # batch 1: (T,)
            t = norms.shape[0]
            start = self._seen[i]
            self.sum_all[i] += norms.sum().double()
            self.n_all[i] += t
            if start == 0:
                self.sum_first[i] += norms[0].double()
                self.n_first[i] += 1
            gen_from = max(self._prompt_len - start, 0)
            if gen_from < t:
                self.sum_gen[i] += norms[gen_from:].sum().double()
                self.n_gen[i] += t - gen_from
            self._seen[i] = start + t
        return hook

    def __enter__(self):
        self._handles = [m.register_forward_hook(self._make_hook(i)) for i, m in enumerate(self.layers)]
        return self

    def __exit__(self, *exc):
        for h in self._handles:
            h.remove()
        self._handles = []
        return False

    def stats(self) -> dict:
        sa, na = self.sum_all.cpu(), self.n_all.cpu()
        sf, nf = self.sum_first.cpu(), self.n_first.cpu()
        sg, ng = self.sum_gen.cpu(), self.n_gen.cpu()
        out = {}
        for i in range(len(self.layers)):
            out[i] = {
                "mean_all": float(sa[i] / na[i]),
                "mean_excl_first": float((sa[i] - sf[i]) / (na[i] - nf[i])),
                "mean_generated": float(sg[i] / ng[i]) if ng[i] > 0 else None,
                "first_token_mean": float(sf[i] / nf[i]) if nf[i] > 0 else None,
            }
        return {"layers": out, "positions": int(self.n_all[0]) if len(self.layers) else 0,
                "positions_generated": int(self.n_gen[0]) if len(self.layers) else 0,
                "sequences": self.sequences}


def layer_norms(recorder: NormRecorder, out_path: str | Path = LAYER_NORMS_PATH, *, seeds, conditions,
                episodes: list[dict], model_name: str, key: str = DEFAULT_NORM_KEY) -> dict[int, float]:
    """Write the recorder's per-layer mean norms with the seeds and turn count used.

    Returns {layer: norm} for `key`, the number the hook uses."""
    if key not in NORM_KEYS:
        raise ValueError(f"key must be one of {NORM_KEYS}")
    st = recorder.stats()
    payload = {
        "model": model_name,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "definition": "mean L2 norm of the output of model.model.layers[L], measured on unsteered critter turns "
                      "(prompt and generated positions, forward passes inside generate), averaged over token positions",
        "hook_key": key,
        "seeds": sorted({int(s) for s in seeds}),
        "conditions": list(conditions),
        "episodes": episodes,
        "turns": int(sum(e["turns"] for e in episodes)),
        "calls": st["sequences"],
        "positions": st["positions"],
        "positions_generated": st["positions_generated"],
        "layers": {str(i): v for i, v in st["layers"].items()},
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return {i: v[key] for i, v in st["layers"].items()}


def load_layer_norms(path: str | Path = LAYER_NORMS_PATH, key: str | None = None) -> dict[int, float]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    key = key or data.get("hook_key", DEFAULT_NORM_KEY)
    if key not in NORM_KEYS:
        raise ValueError(f"key must be one of {NORM_KEYS}")
    return {int(i): float(v[key]) for i, v in data["layers"].items()}


# ---------------------------------------------------------------- measuring the effect
@torch.no_grad()
def measure_change(model, layer: int, prompt_len: int, full_ids: torch.Tensor, delta: torch.Tensor,
                   mode: str = "generated") -> dict:
    """Teacher-forced check of the hook. Runs full_ids (prompt + reply, shape (1, T)) through the
    decoder twice, unsteered and steered, captures the output of `layer` both times and compares.

    At the steered layer the change should equal delta at every steered position and be zero elsewhere."""
    layers = model.model.layers
    captured = {}

    def capture(tag):
        def hook(module, args, output):
            captured[tag] = _hidden(output).detach().float().cpu()[0]
        return hook

    h0 = layers[layer].register_forward_hook(capture("base"))
    try:
        model.model(full_ids, use_cache=False)
    finally:
        h0.remove()
    with SteeringHook(layers[layer], delta, mode, prompt_len):
        h1 = layers[layer].register_forward_hook(capture("steered"))  # runs after the steering hook
        try:
            model.model(full_ids, use_cache=False)
        finally:
            h1.remove()
    base, steered = captured["base"], captured["steered"]
    diff = steered - base
    dn = diff.norm(dim=-1)
    intended = float(delta.float().norm())
    uvec = (delta.float() / delta.float().norm()).cpu()
    gen_idx = torch.arange(base.shape[0]) >= prompt_len
    steered_idx = torch.ones_like(gen_idx) if mode == "all" else gen_idx
    on, off = dn[steered_idx], dn[~steered_idx]
    cos = (diff[steered_idx] @ uvec) / on.clamp_min(1e-9)
    return {
        "layer": layer, "mode": mode, "positions": int(base.shape[0]), "steered_positions": int(steered_idx.sum()),
        "intended_norm": intended,
        "measured_norm_mean": float(on.mean()) if on.numel() else None,
        "measured_norm_min": float(on.min()) if on.numel() else None,
        "measured_norm_max": float(on.max()) if on.numel() else None,
        "measured_over_intended": float(on.mean()) / intended if on.numel() else None,
        "cosine_with_vector_mean": float(cos.mean()) if on.numel() else None,
        "unsteered_positions_max_change": float(off.max()) if off.numel() else 0.0,
        "residual_norm_at_steered_positions_mean": float(base[steered_idx].norm(dim=-1).mean()) if on.numel() else None,
    }
