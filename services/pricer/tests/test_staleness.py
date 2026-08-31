"""Task 4: oldest_input_event_time reflects the genuinely oldest input --
not always equal to as_of, and not always equal to the portfolio's own
positions' as_of_event_time either."""
from datetime import UTC, datetime

from loader import load_tick_fixtures
from pricer_test_helpers import run_fixture_pipeline


def test_oldest_input_event_time_reflects_the_actual_oldest_price(kafka_stack) -> None:
    _, ticks = load_tick_fixtures()
    tick1, tick2, tick3 = (t.event_time for t in ticks)  # AAPL, MSFT, AAPL

    produced = run_fixture_pipeline(kafka_stack)
    by_portfolio_and_as_of = {(s.portfolio_id, s.as_of): s for s in produced}

    # PF-2 only ever holds AAPL directly -- every snapshot is priced
    # entirely off the triggering tick itself, so oldest == as_of always.
    pf2_first = by_portfolio_and_as_of[("PF-2", tick1)]
    assert pf2_first.oldest_input_event_time == tick1 == pf2_first.as_of

    pf2_second = by_portfolio_and_as_of[("PF-2", tick3)]
    assert pf2_second.oldest_input_event_time == tick3 == pf2_second.as_of

    # PF-1's first snapshot is triggered by the MSFT tick (tick2), but
    # AAPL-CALL-150's price is still whatever arrived on tick1 -- older.
    pf1_first = by_portfolio_and_as_of[("PF-1", tick2)]
    assert pf1_first.as_of == tick2
    assert pf1_first.oldest_input_event_time == tick1
    assert pf1_first.oldest_input_event_time < pf1_first.as_of

    # PF-1's second snapshot is triggered by the second AAPL tick (tick3);
    # MSFT-PUT-280's price is still tick2's -- now the older one.
    pf1_second = by_portfolio_and_as_of[("PF-1", tick3)]
    assert pf1_second.oldest_input_event_time == tick2
    assert pf1_second.oldest_input_event_time < pf1_second.as_of


def test_oldest_input_event_time_defaults_to_epoch_for_legacy_records() -> None:
    """The BACKWARD-compatible wire default (docs/domain-model.md,
    contracts/avro/risk-snapshot.avsc) -- a sentinel, not a real value."""
    import json

    from meridian_contracts.risk_snapshot import SCHEMA_JSON

    schema = json.loads(SCHEMA_JSON)
    field = next(f for f in schema["fields"] if f["name"] == "oldest_input_event_time")
    assert field["default"] == 0
    epoch = datetime.fromtimestamp(0, tz=UTC)
    assert epoch.year == 1970
