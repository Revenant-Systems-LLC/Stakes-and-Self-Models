"""A fake Anthropic client for tests and dry runs. It never touches the network.

The script is either a list of steps (one per create() call) or a function
taking the call's keyword arguments and returning a step. Steps:

    reply(text, input_tokens=, output_tokens=, ...)   a normal reply
    refusal(category=, explanation=, ...)             stop_reason "refusal" (content empty)
    garbage(text)                                     a reply that is not valid JSON
    error(status_code, message, error_type=)          raises FakeAPIError (429, 529, 500, 400, 401 ...)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

from world.agents import is_checkin_text
from world.env import MOVES


class FakeAPIError(Exception):
    """Stands in for the SDK's status errors: carries status_code and a message, nothing else."""

    def __init__(self, status_code: int, message: str = "fake API error", error_type: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        # Like the SDK's APIStatusError.body: the parsed JSON body of the error response.
        self.body = {"type": "error", "error": {"type": error_type, "message": message}} if error_type else None


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
    error_type: str | None = None


def reply(text: str, **kw) -> Step:
    return Step("reply", text=text, **kw)


def valid_reply(move: str = "stay", look: int = 4, diary: str = "ok", answer: str = "", **kw) -> Step:
    """A valid four-field reply. answer stays empty unless the test is playing a check-in turn."""
    return reply(json.dumps({"move": move, "look": look, "diary": diary, "answer": answer}), **kw)


def garbage(text: str = "<<not json>>", **kw) -> Step:
    return reply(text, **kw)


def refusal(**kw) -> Step:
    return Step("refusal", stop_reason="refusal", **kw)


def error(status_code: int, message: str = "fake API error", error_type: str | None = None) -> Step:
    return Step("error", status_code=status_code, message=message, error_type=error_type)


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
            raise FakeAPIError(step.status_code, step.message, step.error_type)
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


def random_valid_script(seed: int, *, base_input_tokens: int = 1200, output_tokens: int = 150,
                        checkin_text: str | None = None):
    """For dry runs: valid replies from a seeded RNG. Input tokens grow with the prompt text. On a check-in turn
    (the text holds the game check question, or checkin_text, the question the run is using) the answer field gets a
    yes or no from its own RNG stream; on every other turn it is empty."""
    rng = np.random.default_rng([seed, 99])
    answer_rng = np.random.default_rng([seed, 98])
    marker = checkin_text.strip() if checkin_text and checkin_text.strip() else None

    def script(kwargs):
        text = kwargs["messages"][-1]["content"]
        move = str(rng.choice(MOVES))
        answer = ""
        if is_checkin_text(text) or (marker and marker in text):
            answer = "Yes, something did not match." if answer_rng.integers(0, 2) else "No, nothing looked off."
        return valid_reply(move, int(rng.integers(0, 9)), f"I chose {move}.", answer=answer,
                           input_tokens=base_input_tokens + len(text) // 4, output_tokens=output_tokens)

    return script
