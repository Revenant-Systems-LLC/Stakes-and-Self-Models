"""A fake Anthropic client for tests and dry runs. It never touches the network.

The script is either a list of steps (one per create() call) or a function
taking the call's keyword arguments and returning a step. Steps:

    reply(text, input_tokens=, output_tokens=, ...)   a normal reply
    refusal(category=, explanation=, ...)             stop_reason "refusal" (content empty)
    garbage(text)                                     a reply that is not valid JSON
    error(status_code, message)                       raises FakeAPIError (429, 529, 500, 400 ...)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

from world.env import MOVES


class FakeAPIError(Exception):
    """Stands in for the SDK's status errors: carries status_code and a message, nothing else."""

    def __init__(self, status_code: int, message: str = "fake API error"):
        super().__init__(message)
        self.status_code = status_code


class FakeScriptExhausted(AssertionError):
    pass


@dataclass
class FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation: object = None


@dataclass
class FakeBlock:
    type: str
    text: str | None = None


@dataclass
class FakeRefusalDetails:
    category: str | None = "general_harms"
    explanation: str | None = None
    type: str = "refusal"

    def model_dump(self):
        return {"category": self.category, "explanation": self.explanation, "type": self.type}


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    usage: FakeUsage
    stop_details: object = None
    id: str = "msg_fake"
    model: str = "fake"


@dataclass
class Step:
    kind: str                       # reply | refusal | error
    text: str = ""
    input_tokens: int = 1000
    output_tokens: int = 100
    cache_creation: int = 0
    cache_read: int = 0
    stop_reason: str = "end_turn"
    thinking: bool = True
    category: str | None = "general_harms"
    explanation: str | None = None
    status_code: int = 500
    message: str = "fake API error"


def reply(text: str, **kw) -> Step:
    return Step("reply", text=text, **kw)


def valid_reply(move: str = "stay", look: int = 4, diary: str = "ok", **kw) -> Step:
    return reply(json.dumps({"move": move, "look": look, "diary": diary}), **kw)


def garbage(text: str = "<<not json>>", **kw) -> Step:
    return reply(text, **kw)


def refusal(**kw) -> Step:
    return Step("refusal", stop_reason="refusal", **kw)


def error(status_code: int, message: str = "fake API error") -> Step:
    return Step("error", status_code=status_code, message=message)


class _Messages:
    def __init__(self, owner: "FakeClient"):
        self._owner = owner

    def create(self, **kwargs):
        o = self._owner
        o.calls.append(kwargs)
        if callable(o.script):
            step = o.script(kwargs)
        else:
            if o._next >= len(o.script):
                raise FakeScriptExhausted(f"fake script has {len(o.script)} steps, call {o._next + 1} has none")
            step = o.script[o._next]
            o._next += 1
        if step.kind == "error":
            raise FakeAPIError(step.status_code, step.message)
        usage = FakeUsage(step.input_tokens, step.output_tokens, step.cache_creation, step.cache_read)
        if step.kind == "refusal":
            return FakeResponse([], "refusal", usage, FakeRefusalDetails(step.category, step.explanation),
                                model=kwargs.get("model", "fake"))
        blocks = ([FakeBlock("thinking")] if step.thinking else []) + [FakeBlock("text", step.text)]
        return FakeResponse(blocks, step.stop_reason, usage, model=kwargs.get("model", "fake"))


@dataclass
class FakeClient:
    script: object = field(default_factory=list)
    calls: list = field(default_factory=list)
    _next: int = 0

    def __post_init__(self):
        self.messages = _Messages(self)


def random_valid_script(seed: int, *, base_input_tokens: int = 1200, output_tokens: int = 150):
    """For dry runs: valid replies from a seeded RNG. Input tokens grow with the prompt text."""
    rng = np.random.default_rng([seed, 99])

    def script(kwargs):
        text = kwargs["messages"][-1]["content"]
        move = str(rng.choice(MOVES))
        return valid_reply(move, int(rng.integers(0, 9)), f"I chose {move}.",
                           input_tokens=base_input_tokens + len(text) // 4, output_tokens=output_tokens)

    return script
