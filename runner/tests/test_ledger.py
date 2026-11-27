import json

import pytest

from runner.ledger import CapExceeded, Ledger, LedgerError, PriceError, PriceTable, Usage
from runner.tests.helpers import PRICE_FILE


@pytest.fixture
def prices():
    return PriceTable.load(PRICE_FILE)


def test_price_file_carries_source_and_date(prices):
    raw = json.loads(PRICE_FILE.read_text(encoding="utf-8"))
    assert raw["read_on"] == "2026-11-26" and "Anthropic pricing page" in raw["source"]
    assert raw["unit"] == "USD per million tokens"
    for m in ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"):
        prices.require(m)


def test_missing_price_is_refused(prices):
    with pytest.raises(PriceError, match="no price entry"):
        prices.require("claude-nonesuch")
    with pytest.raises(PriceError):
        PriceTable({"source": "x", "models": {}})  # no read_on date


# Hand arithmetic, per million tokens.
def test_sonnet_cost_with_cache(prices):
    # 10,000 in x 2.00 + 1,000 cache write (5 min) x 2.50 + 5,000 cache read x 0.10 + 2,000 out x 10.00
    # = 20,000 + 2,500 + 500 + 20,000 = 43,000 micro-dollars
    u = Usage(input_tokens=10_000, output_tokens=2_000, cache_creation_tokens=1_000, cache_read_tokens=5_000)
    assert prices.cost("claude-sonnet-5-5", u) == pytest.approx(0.043)


def test_opus_cost_splits_cache_write_by_ttl(prices):
    # 3,000 x 4.00 + (2,000 - 800) 5-min writes x 5.00 + 800 1-hour writes x 8.00 + 10,000 reads x 0.20 + 500 out x 20.00
    # = 12,000 + 6,000 + 6,400 + 2,000 + 10,000 = 36,400
    u = Usage(input_tokens=3_000, output_tokens=500, cache_creation_tokens=2_000, cache_creation_1h_tokens=800,
              cache_read_tokens=10_000)
    assert prices.cost("claude-opus-5-5", u) == pytest.approx(0.0364)


def test_haiku_cost_at_and_over_100k_prompt_tokens(prices):
    # 70,000 prompt tokens (50,000 in + 20,000 read): cheap tier. 50,000 x 0.10 + 20,000 x 0.01 + 1,000 out x 0.50 = 5,700
    under = Usage(input_tokens=50_000, output_tokens=1_000, cache_read_tokens=20_000)
    assert prices.cost("claude-haiku-5-5", under) == pytest.approx(0.0057)
    # exactly 100,000 prompt tokens is still the cheap tier: 100,000 x 0.10 = 10,000
    assert prices.cost("claude-haiku-5-5", Usage(input_tokens=100_000)) == pytest.approx(0.01)
    # 100,001 is the dear tier: 100,001 x 0.50
    assert prices.cost("claude-haiku-5-5", Usage(input_tokens=100_001)) == pytest.approx(0.0500005)
    # 110,000 prompt tokens (60,000 in + 30,000 5-min writes + 20,000 reads), 1,000 out, all at the dear rates:
    # 60,000 x 0.50 + 30,000 x 0.625 + 20,000 x 0.05 + 1,000 x 2.50 = 30,000 + 18,750 + 1,000 + 2,500 = 52,250
    over = Usage(input_tokens=60_000, output_tokens=1_000, cache_creation_tokens=30_000, cache_read_tokens=20_000)
    assert prices.cost("claude-haiku-5-5", over) == pytest.approx(0.05225)


def test_response_line_has_every_field_and_is_priced(tmp_path, prices):
    led = Ledger(tmp_path, "pilot", 100, prices)
    cost = led.record_response(model="claude-sonnet-5-5", episode_id="e1", turn=3, attempt=1,
                               usage=Usage(10_000, 2_000, 1_000, 5_000))
    assert cost == pytest.approx(0.043)
    (line,) = [json.loads(l) for l in led.path.read_text(encoding="utf-8").splitlines()]
    assert line["type"] == "response" and line["phase"] == "pilot" and line["model"] == "claude-sonnet-5-5"
    assert line["episode_id"] == "e1" and line["turn"] == 3 and line["attempt"] == 1 and line["time"]
    assert (line["input_tokens"], line["output_tokens"], line["cache_creation_input_tokens"],
            line["cache_read_input_tokens"]) == (10_000, 2_000, 1_000, 5_000)
    assert line["cost_usd"] == pytest.approx(0.043)


def test_spend_survives_a_restart(tmp_path, prices):
    led = Ledger(tmp_path, "pilot", 100, prices)
    for turn in range(1, 4):
        led.record_response(model="claude-opus-5-5", episode_id="e1", turn=turn, usage=Usage(1_000, 1_000))
    expected = 3 * (1_000 * 4 + 1_000 * 20) / 1e6
    assert led.spend == pytest.approx(expected)
    again = Ledger(tmp_path, "pilot", 100, prices)  # a fresh process re-reads the file
    assert again.spend == pytest.approx(expected)
    again.record_response(model="claude-opus-5-5", episode_id="e2", turn=1, usage=Usage(1_000, 1_000))
    assert led.spend == pytest.approx(expected + 0.024)  # the first instance sees the second one's line
    assert Ledger(tmp_path, "confirmatory", 750, prices).spend == 0  # phases are separate ledgers


def test_a_cut_off_line_stops_the_runner_rather_than_forgetting_money(tmp_path, prices):
    led = Ledger(tmp_path, "pilot", 100, prices)
    led.record_response(model="claude-opus-5-5", episode_id="e1", turn=1, usage=Usage(1_000, 1_000))
    with open(led.path, "ab") as f:
        f.write(b'{"type":"response","cost_us')
    with pytest.raises(LedgerError, match="middle of a line"):
        Ledger(tmp_path, "pilot", 100, prices)


def test_garbled_or_foreign_lines_are_errors(tmp_path, prices):
    path = tmp_path / "ledger" / "pilot.jsonl"
    path.parent.mkdir()
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(LedgerError):
        Ledger(tmp_path, "pilot", 100, prices)
    path.write_text(json.dumps({"type": "response", "phase": "reserve", "cost_usd": 1, "episode_id": "x"}) + "\n", encoding="utf-8")
    with pytest.raises(LedgerError, match="phase"):
        Ledger(tmp_path, "pilot", 100, prices)


def test_start_check_uses_the_prior_then_the_running_mean(tmp_path, prices):
    led = Ledger(tmp_path, "pilot", 1.0, prices)
    # $0.20 spent on a Haiku episode that has not finished: 400,000 output tokens x 0.50 per million.
    led.record_response(model="claude-haiku-5-5", episode_id="h1", turn=1, usage=Usage(output_tokens=400_000))
    assert led.spend == pytest.approx(0.20)

    c = led.start_check("claude-sonnet-5-5", prior_usd=0.45)  # no finished Sonnet episode yet: prior
    assert c.basis == "prior" and c.expected_cost == 0.45
    assert not c.ok  # 0.20 + 2 x 0.45 = 1.10 passes the 1.00 cap
    assert led.start_check("claude-haiku-5-5", prior_usd=0.03).ok  # 0.20 + 0.06 does not

    # One finished Sonnet episode costing $0.05 (5,000 output tokens x 10.00 per million).
    led.record_response(model="claude-sonnet-5-5", episode_id="s1", turn=1, usage=Usage(output_tokens=5_000))
    led.record_episode_end(model="claude-sonnet-5-5", episode_id="s1", status="done")
    c = led.start_check("claude-sonnet-5-5", prior_usd=0.45)
    assert c.basis == "running mean" and c.expected_cost == pytest.approx(0.05)
    assert c.ok  # 0.25 + 2 x 0.05 = 0.35

    # An aborted or failed episode does not drag the mean down.
    led.record_response(model="claude-sonnet-5-5", episode_id="s2", turn=1, usage=Usage(output_tokens=1_000))
    led.record_episode_end(model="claude-sonnet-5-5", episode_id="s2", status="aborted_cap")
    assert led.mean_episode_cost("claude-sonnet-5-5") == pytest.approx(0.05)

    # Now the mean itself is too dear: spend 0.26, mean 0.50 after a second finished episode of $0.95.
    led.record_response(model="claude-sonnet-5-5", episode_id="s3", turn=1, usage=Usage(output_tokens=95_000))
    led.record_episode_end(model="claude-sonnet-5-5", episode_id="s3", status="done")
    c = led.start_check("claude-sonnet-5-5", prior_usd=0.45)
    assert c.basis == "running mean" and c.expected_cost == pytest.approx(0.50) and not c.ok


def test_episode_end_lines_are_not_summed_into_spend(tmp_path, prices):
    led = Ledger(tmp_path, "pilot", 100, prices)
    led.record_response(model="claude-sonnet-5-5", episode_id="s1", turn=1, usage=Usage(output_tokens=5_000))
    led.record_episode_end(model="claude-sonnet-5-5", episode_id="s1", status="done")
    assert Ledger(tmp_path, "pilot", 100, prices).spend == pytest.approx(0.05)


def test_check_cap_trips_only_when_spend_passes_the_cap(tmp_path, prices):
    led = Ledger(tmp_path, "pilot", 0.05, prices)
    led.record_response(model="claude-sonnet-5-5", episode_id="s1", turn=1, usage=Usage(output_tokens=5_000))
    led.check_cap()  # exactly at the cap: not passed
    led.record_response(model="claude-sonnet-5-5", episode_id="s1", turn=2, usage=Usage(output_tokens=1))
    with pytest.raises(CapExceeded) as e:
        led.check_cap()
    assert e.value.spend > 0.05 and e.value.cap == 0.05
