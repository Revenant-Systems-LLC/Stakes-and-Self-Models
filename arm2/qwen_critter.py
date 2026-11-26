"""Arm 2 critter: Qwen2.5-7B-Instruct in 4-bit NF4 as a world Agent.

System prompt: prompts/critter_stakes.txt or prompts/critter_no_stakes.txt by
condition. User message: the turn text from world/observe.py, unchanged.
Sampling: the model's own generation_config (temperature, top_p, top_k,
repetition_penalty) with max_new_tokens 120, seeded per call from
(episode seed, turn, attempt), so a rerun gives the same replies.

The reply is returned raw. world/agents.py decides validity. world/episode.py
writes tokens_in/tokens_out as null, so those, the timing and the sampling and
steering settings go in a sidecar file next to each episode log.

Runs from the Lobster-Lab venv with the weights already cached under its
hf_home. Offline mode is forced so nothing can be downloaded.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import nullcontext
from pathlib import Path

os.environ.setdefault("HF_HOME", r"M:\Projects\Lobster-Lab\hf_home")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import torch
from tqdm import tqdm

from arm2 import steering
from world.env import CONDITIONS

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
MAX_NEW_TOKENS = 120
REPO = Path(__file__).resolve().parent.parent
PROMPT_FILES = {"stakes": REPO / "prompts" / "critter_stakes.txt",
                "no_stakes": REPO / "prompts" / "critter_no_stakes.txt"}
SAMPLING_KEYS = ("do_sample", "temperature", "top_p", "top_k", "repetition_penalty", "eos_token_id", "pad_token_id")


def read_system_prompt(condition: str) -> str:
    if condition not in PROMPT_FILES:
        raise ValueError(f"condition must be one of {CONDITIONS}")
    return PROMPT_FILES[condition].read_text(encoding="utf-8")


def turn_seed(episode_seed: int, turn: int, attempt: int) -> int:
    """Sampling seed for one call. Same (episode seed, turn, attempt) gives the same number."""
    return int(np.random.SeedSequence([int(episode_seed), int(turn), int(attempt)]).generate_state(1)[0])


def is_fenced(text: str) -> bool:
    return "```" in text


def load_model(model_id: str = MODEL_ID):
    """4-bit NF4, double quantisation, float16 compute (003b found no reason to change this)."""
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                               bnb_4bit_compute_dtype=torch.float16,
                                               bnb_4bit_use_double_quant=True),
        device_map="cuda:0",
    ).eval()
    return model, tok


class QwenCritter:
    """One loaded model, any number of episodes. Call begin_episode() before run_episode()
    and end_episode() after it."""

    name = "qwen2.5-7b-instruct-nf4"

    def __init__(self, model=None, tokenizer=None, *, max_new_tokens: int = MAX_NEW_TOKENS):
        self.model, self.tok = model, tokenizer
        self.max_new_tokens = max_new_tokens
        self.layer_norms: dict[int, float] | None = None
        self.steering: steering.SteeringSpec | None = None
        self.recorder: steering.NormRecorder | None = None  # set to measure layer norms on unsteered turns
        self.keep_trace = False
        self.trace: list[dict] = []
        self.calls: list[dict] = []
        self._unit_tensor = None
        self._magnitude = 0.0
        self._sidecar = None
        self._bar = None
        self._reset_episode_state()

    # ------------------------------------------------------------ settings
    def sampling_settings(self) -> dict:
        gc = self.model.generation_config.to_dict() if self.model is not None else {}
        out = {k: gc.get(k) for k in SAMPLING_KEYS}
        out["max_new_tokens"] = self.max_new_tokens
        out["seeded_from"] = "SeedSequence([episode_seed, turn, attempt]).generate_state(1)[0] into torch.manual_seed"
        return out

    def set_steering(self, spec: steering.SteeringSpec | None):
        """Steer the turns spec.turns (every turn if None). Needs layer norms. None switches steering off."""
        if spec is None:
            self.steering, self._unit_tensor, self._magnitude = None, None, 0.0
            return
        if self.layer_norms is None:
            raise RuntimeError("load layer norms before steering (critter.layer_norms = load_layer_norms())")
        if spec.layer not in self.layer_norms:
            raise ValueError(f"no layer norm for layer {spec.layer}")
        if self.model is not None:
            width = self.model.config.hidden_size
            if spec.vector.shape[0] != width:
                raise ValueError(f"vector has {spec.vector.shape[0]} entries, model width is {width}")
        self.steering = spec
        self._magnitude = steering.magnitude(spec.strength, spec.layer, self.layer_norms)
        self._unit_tensor = torch.from_numpy(spec.vector)

    def steering_description(self) -> dict | None:
        s = self.steering
        if s is None:
            return None
        return {"layer": s.layer, "strength": s.strength, "mode": s.mode, "turns": None if s.turns is None else sorted(s.turns),
                "scale": steering.SCALE, "layer_norm": self.layer_norms[s.layer], "magnitude": self._magnitude,
                "vector_sha256": hashlib.sha256(s.vector.tobytes()).hexdigest()[:16]}

    # ------------------------------------------------------------ episodes
    def _reset_episode_state(self):
        self._seed = None
        self._condition = None
        self._system = None
        self._last_turn = None
        self._attempt = 0
        self._turn_seconds = 0.0

    def begin_episode(self, seed: int, condition: str, *, sidecar_path: str | Path | None = None, desc: str = "episode",
                      total_turns: int = 48, progress: bool = True):
        if condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {CONDITIONS}")
        self._reset_episode_state()
        self._seed, self._condition = int(seed), condition
        self._system = read_system_prompt(condition)
        self.calls, self.trace = [], []
        if sidecar_path is not None:
            sidecar_path = Path(sidecar_path)
            sidecar_path.parent.mkdir(parents=True, exist_ok=True)
            self._sidecar = open(sidecar_path, "w", encoding="utf-8")
            self._write_sidecar({"type": "meta", "model": MODEL_ID, "name": self.name, "world_seed": self._seed,
                                 "condition": condition, "sampling": self.sampling_settings(),
                                 "steering": self.steering_description(),
                                 "system_prompt_file": PROMPT_FILES[condition].name,
                                 "system_prompt_sha256": hashlib.sha256(self._system.encode("utf-8")).hexdigest()[:16],
                                 "torch": torch.__version__,
                                 "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"})
        self._bar = tqdm(total=total_turns, desc=desc, unit="turn", dynamic_ncols=True, mininterval=1.0,
                         disable=not progress)

    def end_episode(self, summary: dict | None = None):
        if self._bar is not None:
            if summary:
                self._bar.set_postfix_str(f"done: {summary.get('turns')} turns, fainted={summary.get('fainted')}, "
                                          f"food={summary.get('food_eaten')}, thorns={summary.get('thorns_hit')}")
            self._bar.close()
            self._bar = None
        if self._sidecar is not None:
            if summary:
                self._write_sidecar({"type": "end", **{k: v for k, v in summary.items() if k != "schedule"}})
            self._sidecar.close()
            self._sidecar = None

    def _write_sidecar(self, obj: dict):
        self._sidecar.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._sidecar.flush()

    # ------------------------------------------------------------ the Agent protocol
    def reply(self, observation: dict, text: str) -> str:
        if self._seed is None:
            raise RuntimeError("call begin_episode() before run_episode()")
        turn = int(observation["turn"])
        self._attempt = self._attempt + 1 if turn == self._last_turn else 0
        if self._attempt == 0:
            self._turn_seconds = 0.0
        self._last_turn = turn
        seed = turn_seed(self._seed, turn, self._attempt)
        steer = self.steering is not None and self.steering.applies(turn)

        t0 = time.perf_counter()
        prompt_ids = self._encode(self._system, text)
        reply_ids = self._generate_ids(prompt_ids, seed, steer)
        raw = self._decode(reply_ids)
        seconds = time.perf_counter() - t0
        self._turn_seconds += seconds

        eos = self._eos_ids()
        n_out = len(reply_ids)
        rec = {"type": "call", "turn": turn, "attempt": self._attempt, "seed": seed,
               "tokens_in": len(prompt_ids), "tokens_out": n_out, "seconds": round(seconds, 3),
               "hit_cap": n_out >= self.max_new_tokens and (not reply_ids or reply_ids[-1] not in eos),
               "fenced": is_fenced(raw), "steered": steer}
        if steer:
            rec.update(layer=self.steering.layer, strength=self.steering.strength, mode=self.steering.mode,
                       magnitude=round(self._magnitude, 3))
        self.calls.append(rec)
        if self._sidecar is not None:
            self._write_sidecar(rec)
        if self.keep_trace:
            self.trace.append({**rec, "prompt_ids": list(prompt_ids), "reply_ids": list(reply_ids), "reply": raw})
        if self._bar is not None:
            if self._attempt == 0:
                self._bar.update(1)
            retries = sum(c["attempt"] > 0 for c in self.calls)
            self._bar.set_postfix_str(f"t{turn} {seconds:.1f}s {n_out}tok retries={retries}")
        return raw

    # ------------------------------------------------------------ model calls (overridden in tests)
    def _eos_ids(self) -> set[int]:
        eos = self.model.generation_config.eos_token_id if self.model is not None else None
        return set(eos) if isinstance(eos, (list, tuple)) else ({eos} if eos is not None else set())

    def _encode(self, system: str, user: str) -> list[int]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        enc = self.tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        return enc["input_ids"][0].tolist()

    def _decode(self, ids: list[int]) -> str:
        return self.tok.decode(ids, skip_special_tokens=True)

    @torch.no_grad()
    def _generate_ids(self, prompt_ids: list[int], seed: int, steer: bool) -> list[int]:
        device = self.model.device
        input_ids = torch.tensor([prompt_ids], device=device)
        ctx = nullcontext()
        if steer:
            s = self.steering
            delta = self._unit_tensor.to(device) * self._magnitude
            ctx = steering.SteeringHook(self.model.model.layers[s.layer], delta, s.mode, prompt_len=len(prompt_ids))
        if self.recorder is not None:
            self.recorder.start_sequence(len(prompt_ids))
        torch.manual_seed(seed)
        with ctx:
            out = self.model.generate(input_ids=input_ids, attention_mask=torch.ones_like(input_ids),
                                      max_new_tokens=self.max_new_tokens, pad_token_id=self.tok.pad_token_id)
        return out[0, input_ids.shape[1]:].tolist()

    def generate_from_ids(self, prompt_ids: list[int], seed: int, steer: bool) -> str:
        """Re-run one call from stored token ids and its seed (used by the smoke checks)."""
        return self._decode(self._generate_ids(prompt_ids, seed, steer))
