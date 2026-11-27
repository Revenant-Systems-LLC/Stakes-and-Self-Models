import pytest

from runner.claude_critter import APIFailure, ClaudeCritter
from runner.fake_client import FakeClient, FakeScriptExhausted, error, garbage, refusal, valid_reply
from runner.ledger import Ledger, PriceTable
from runner.tests.helpers import PRICE_FILE
from world.agents import decide

OBS = {"turn": 1}


def make(tmp_path, steps, *, model="claude-haiku-5-5", sleeps=None, **kw):
    ledger = Ledger(tmp_path, "dev", 10, PriceTable.load(PRICE_FILE))
    client = FakeClient(steps)
    critter = ClaudeCritter(client, model=model, system_prompt="TEST system", ledger=ledger, episode_id="e1",
                            sleep=(sleeps.append if sleeps is not None else (lambda s: None)), **kw)
    return critter, client, ledger


def test_request_carries_only_the_preregistered_settings(tmp_path):
    critter, client, _ = make(tmp_path, [valid_reply("north", 2, "hi")])
    raw = critter.reply({"turn": 4}, "TURN TEXT")
    assert raw == '{"move": "north", "look": 2, "diary": "hi", "answer": ""}'
    (req,) = client.calls
    assert set(req) == {"model", "max_tokens", "system", "messages", "output_config"}
    assert req["model"] == "claude-haiku-5-5" and req["max_tokens"] == 2000
    assert req["output_config"] == {"effort": "low"}  # effort only: no structured-output format
    assert req["system"] == "TEST system"
    assert req["messages"] == [{"role": "user", "content": "TURN TEXT"}]  # one fresh message, nothing carried over
    for banned in ("thinking", "temperature", "top_p", "top_k", "tools", "tool_choice", "betas", "stop_sequences"):
        assert banned not in req


def test_max_tokens_and_effort_are_configurable(tmp_path):
    critter, client, _ = make(tmp_path, [valid_reply()], max_tokens=123, effort="medium")
    critter.reply(OBS, "x")
    assert client.calls[0]["max_tokens"] == 123 and client.calls[0]["output_config"] == {"effort": "medium"}


def test_thinking_blocks_are_not_part_of_the_reply(tmp_path):
    critter, _, _ = make(tmp_path, [valid_reply(thinking=True)])
    assert critter.reply(OBS, "x").startswith("{")


def test_each_call_is_priced_into_the_ledger_and_the_call_record(tmp_path):
    critter, _, ledger = make(tmp_path, [valid_reply(input_tokens=2_000, output_tokens=300, cache_read=500)],
                              model="claude-sonnet-5-5")
    critter.reply({"turn": 9}, "x")
    (call,) = critter.take_calls()
    expected = (2_000 * 2.00 + 500 * 0.10 + 300 * 10.00) / 1e6
    assert call["cost_usd"] == pytest.approx(expected) == pytest.approx(ledger.spend)
    assert call["input_tokens"] == 2_000 and call["output_tokens"] == 300 and call["cache_read_input_tokens"] == 500
    assert call["prompt_tokens"] == 2_500 and call["stop_reason"] == "end_turn" and call["turn"] == 9
    assert critter.take_calls() == []


def test_refusal_is_a_bad_reply_with_one_retry_then_stay_and_it_is_logged(tmp_path):
    critter, client, _ = make(tmp_path, [refusal(category="cyber", explanation="no"), refusal()])
    d = decide(critter, {"turn": 5}, "x", fallback_look=7)
    assert not d.valid and len(client.calls) == 2  # one retry, then give up
    assert d.action == {"move": "stay", "look": 7, "diary": "", "answer": ""}
    assert len(d.raw_replies) == 2 and len(d.errors) == 2
    first, second = critter.take_calls()
    assert first["stop_reason"] == "refusal" and first["stop_details"]["category"] == "cyber"
    assert (first["attempt"], second["attempt"]) == (0, 1)
    assert critter.n_refusals == 2  # counted, never dropped


def test_refusal_then_a_good_reply_is_accepted_on_the_retry(tmp_path):
    critter, _, _ = make(tmp_path, [refusal(), valid_reply("east")])
    d = decide(critter, {"turn": 5}, "x", fallback_look=4)
    assert d.valid and d.action["move"] == "east" and len(d.errors) == 1


def test_garbage_gets_one_retry_then_stays(tmp_path):
    critter, client, _ = make(tmp_path, [garbage("<<one>>"), garbage("<<two>>"), valid_reply()])
    d = decide(critter, {"turn": 3}, "x", fallback_look=2)
    assert not d.valid and d.raw_replies == ["<<one>>", "<<two>>"] and len(client.calls) == 2
    assert d.action["move"] == "stay"
    nxt = decide(critter, {"turn": 4}, "x", fallback_look=2)  # the next turn gets a fresh pair of attempts
    assert nxt.valid and [c["attempt"] for c in critter.take_calls()] == [0, 1, 0]


def test_max_tokens_stop_reason_is_logged_and_the_cut_off_text_is_a_bad_reply(tmp_path):
    critter, _, _ = make(tmp_path, [garbage('{"move": "no', stop_reason="max_tokens"), valid_reply()])
    d = decide(critter, {"turn": 3}, "x", fallback_look=2)
    assert d.valid and len(d.errors) == 1
    assert critter.take_calls()[0]["stop_reason"] == "max_tokens"


def test_rate_limit_and_overload_are_retried_with_backoff(tmp_path):
    sleeps = []
    critter, client, ledger = make(tmp_path, [error(429), error(529), valid_reply()], sleeps=sleeps, max_retries=5)
    assert critter.reply({"turn": 1}, "x").startswith("{")
    assert sleeps == [2.0, 4.0] and len(client.calls) == 3 and critter.n_retries == 2
    assert critter.take_calls()[0]["api_retries"] == 2
    assert ledger.spend > 0 and sum(1 for _ in open(ledger.path)) == 1  # failed calls have no usage, so no ledger line


def test_server_errors_are_retried_then_raise_as_an_api_failure(tmp_path):
    sleeps = []
    critter, client, ledger = make(tmp_path, [error(500)] * 4, sleeps=sleeps, max_retries=2, backoff_base=3, backoff_max=5)
    with pytest.raises(APIFailure) as e:
        critter.reply({"turn": 1}, "x")
    assert len(client.calls) == 3  # first try plus two retries
    assert sleeps == [3, 5]  # exponential, capped at backoff_max
    assert e.value.attempts == 3 and e.value.status_codes == [500, 500, 500] and e.value.retryable
    assert ledger.spend == 0


def test_a_400_is_never_retried(tmp_path):
    sleeps = []
    critter, client, _ = make(tmp_path, [error(400, "bad request"), valid_reply()], sleeps=sleeps)
    with pytest.raises(APIFailure) as e:
        critter.reply({"turn": 1}, "x")
    assert len(client.calls) == 1 and sleeps == [] and not e.value.retryable and e.value.status_codes == [400]


def test_connection_errors_are_retried(tmp_path):
    class APIConnectionError(Exception):  # same class name as the SDK's, no status code
        pass

    n = {"i": 0}

    def script(kwargs):
        n["i"] += 1
        if n["i"] == 1:
            raise APIConnectionError("connection reset")
        return valid_reply()

    critter, client, _ = make(tmp_path, script)
    assert critter.reply({"turn": 1}, "x").startswith("{") and n["i"] == 2


def test_a_non_api_exception_is_a_crash_not_an_api_failure(tmp_path):
    def script(kwargs):
        raise TypeError("harness bug")

    critter, _, _ = make(tmp_path, script)
    with pytest.raises(TypeError):
        critter.reply({"turn": 1}, "x")
    with pytest.raises(FakeScriptExhausted):
        make(tmp_path, [])[0].reply({"turn": 1}, "x")


def test_the_critter_module_never_imports_the_anthropic_package():
    import runner.claude_critter as m
    src = open(m.__file__, encoding="utf-8").read()
    assert "import anthropic" not in src and "from anthropic" not in src
