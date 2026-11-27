"""The Claude critter: a world Agent that plays through the Anthropic Messages API.

One fresh call per turn, nothing carried over except what the observation text
holds (the diary). Settings are fixed by the preregistration: effort low
through output_config, thinking parameter omitted (always on for Opus 5.5, so
all three tiers match), no temperature, top_p or top_k, no structured outputs,
no tools, no server-side fallbacks. The reply comes back raw; world/agents.py
decides whether it is valid and applies the one-retry rule, so Arm 1 and Arm 2
judge replies the same way.

The anthropic package is never imported here. The client is passed in (the
real one comes from runner/gate.py, a fake one from runner/fake_client.py).
"""

from __future__ import annotations

import re
import time

from runner.ledger import Ledger, Usage

_RETRY_STATUS = (408, 429)       # 429 rate limit; 408 request timeout. 5xx and 529 (overloaded) are >= 500
_CONNECTION_ERRORS = {"APIConnectionError", "APITimeoutError"}
_KEY_SHAPE = re.compile(r"sk-ant-[A-Za-z0-9_\-]+")


class APIFailure(RuntimeError):
    """An API call failed for good (retries used up, or an error that is not retried)."""

    def __init__(self, message: str, *, attempts: int, status_codes: list, error_type: str, retryable: bool):
        super().__init__(message)
        self.attempts, self.status_codes, self.error_type, self.retryable = attempts, status_codes, error_type, retryable

    def as_dict(self) -> dict:
        return {"message": str(self), "attempts": self.attempts, "status_codes": self.status_codes,
                "error_type": self.error_type, "retryable": self.retryable}


class AuthFailure(RuntimeError):
    """The API refused the key (HTTP 401 or an authentication_error): it expired, was revoked or is wrong.
    The whole run stops at once. The message is fixed on purpose: nothing from the exception, which could
    echo part of a key, is carried into it."""

    def __init__(self):
        super().__init__("the API refused the key (HTTP 401 / authentication_error)")


class AccessFailure(RuntimeError):
    """The API says this key may not use the model (HTTP 403 permission_error) or that the model is not there
    (HTTP 404 not_found_error). The whole run stops at once. Retrying cannot help, the pair is not an exclusion, and
    no other model is ever tried in its place. The message carries only the status and error type, never the API's text."""

    def __init__(self, status_code: int | None, error_type: str):
        super().__init__(f"the API refused access to the model (HTTP {status_code} / {error_type})")
        self.status_code, self.error_type = status_code, error_type


_ACCESS_TYPES = {403: "permission_error", 404: "not_found_error"}


def access_error_type(exc: BaseException) -> str | None:
    """"permission_error" or "not_found_error" if exc is HTTP 403 or 404, or its body names one of those types;
    else None. A 403 or 404 counts whatever the body says: both mean this key cannot get this model."""
    status = getattr(exc, "status_code", None)
    if status in _ACCESS_TYPES and not isinstance(status, bool):
        return _ACCESS_TYPES[status]
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        for t in (body.get("type"), inner.get("type") if isinstance(inner, dict) else None):
            if t in _ACCESS_TYPES.values():
                return t
    return None


def is_auth_error(exc: BaseException) -> bool:
    """HTTP 401, or an error body of type authentication_error (the SDK's body is either the whole
    {"type": "error", "error": {...}} object or just the inner one)."""
    if getattr(exc, "status_code", None) == 401:
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        return "authentication_error" in (body.get("type"), inner.get("type") if isinstance(inner, dict) else None)
    return False


def classify_error(exc: BaseException) -> str | None:
    """"auth", "access", "retry", "fatal", or None when exc is not an API error at all (then it is a harness crash)."""
    if is_auth_error(exc):
        return "auth"
    if access_error_type(exc):
        return "access"
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return "retry" if status in _RETRY_STATUS or status >= 500 else "fatal"
    if any(c.__name__ in _CONNECTION_ERRORS for c in type(exc).__mro__):
        return "retry"
    return None


def _scrub(text: str) -> str:
    return _KEY_SHAPE.sub("[redacted]", str(text))[:300]


def usage_of(resp) -> Usage:
    u = resp.usage
    breakdown = getattr(u, "cache_creation", None)
    return Usage(
        input_tokens=int(u.input_tokens),
        output_tokens=int(u.output_tokens),
        cache_creation_tokens=int(getattr(u, "cache_creation_input_tokens", None) or 0),
        cache_read_tokens=int(getattr(u, "cache_read_input_tokens", None) or 0),
        cache_creation_1h_tokens=int(getattr(breakdown, "ephemeral_1h_input_tokens", 0) or 0) if breakdown is not None else 0,
    )


def _details(obj):
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj if isinstance(obj, dict) else str(obj)


class ClaudeCritter:
    def __init__(self, client, *, model: str, system_prompt: str, ledger: Ledger, episode_id: str,
                 max_tokens: int = 2000, effort: str = "low", max_retries: int = 5,
                 backoff_base: float = 2.0, backoff_max: float = 60.0, sleep=time.sleep):
        self.client, self.model, self.name = client, model, model
        self.system_prompt, self.ledger, self.episode_id = system_prompt, ledger, episode_id
        self.max_tokens, self.effort = max_tokens, effort
        self.max_retries, self.backoff_base, self.backoff_max, self.sleep = max_retries, backoff_base, backoff_max, sleep
        self._last_turn = None
        self._attempt = 0
        self.pending: list[dict] = []   # call records since the last take_calls()
        self.n_calls = 0
        self.n_refusals = 0
        self.n_retries = 0              # SDK-level retries (rate limits, overloads, server errors)

    def take_calls(self) -> list[dict]:
        calls, self.pending = self.pending, []
        return calls

    def _create(self, text: str):
        request = dict(model=self.model, max_tokens=self.max_tokens, system=self.system_prompt,
                       messages=[{"role": "user", "content": text}], output_config={"effort": self.effort})
        statuses: list = []
        while True:
            try:
                return self.client.messages.create(**request)
            except Exception as exc:
                kind = classify_error(exc)
                if kind is None:
                    raise  # not an API error: a harness crash, not an API failure
                if kind == "auth":
                    raise AuthFailure() from None  # no retry, and nothing from exc: it could echo a key
                if kind == "access":
                    raise AccessFailure(getattr(exc, "status_code", None), access_error_type(exc)) from None
                statuses.append(getattr(exc, "status_code", None))
                if kind == "fatal" or len(statuses) > self.max_retries:
                    raise APIFailure(f"{type(exc).__name__}: {_scrub(exc)}", attempts=len(statuses), status_codes=statuses,
                                     error_type=type(exc).__name__, retryable=kind == "retry") from exc
                self.n_retries += 1
                self.sleep(min(self.backoff_max, self.backoff_base * 2 ** (len(statuses) - 1)))

    def reply(self, observation: dict, text: str) -> str:
        turn = int(observation["turn"])
        self._attempt = self._attempt + 1 if turn == self._last_turn else 0
        self._last_turn = turn
        retries_before = self.n_retries
        resp = self._create(text)
        usage = usage_of(resp)
        cost = self.ledger.record_response(model=self.model, episode_id=self.episode_id, turn=turn, usage=usage,
                                           attempt=self._attempt)
        self.n_calls += 1
        stop = getattr(resp, "stop_reason", None)
        self.pending.append({
            "turn": turn, "attempt": self._attempt, "stop_reason": stop,
            "stop_details": _details(getattr(resp, "stop_details", None)),
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "cache_creation_input_tokens": usage.cache_creation_tokens,
            "cache_read_input_tokens": usage.cache_read_tokens,
            "prompt_tokens": usage.prompt_tokens, "cost_usd": cost, "api_retries": self.n_retries - retries_before,
        })
        self.ledger.check_cap()  # after the response is on the books and in the call record; stops everything at once
        if stop == "refusal":
            self.n_refusals += 1
            return ""  # a refusal is a bad reply: world/agents.decide() retries once, then the turn stays
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text" and b.text)
