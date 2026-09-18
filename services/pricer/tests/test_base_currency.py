"""ADR-0028 Decisions 1, 2 and 6: `portfolio.state` carries the portfolio's
reporting currency, a portfolio whose currency is unknown (empty string) is
refused with `UNKNOWN_BASE_CURRENCY` rather than priced under an assumed
one, and every published snapshot records the currency. No conversion
happens yet, so no numeric value depends on the currency in these tests."""
import dataclasses
import logging

from loader import load_portfolio_fixtures, load_tick_fixtures
from pricer.pricing import UnpriceableReason
from pricer_test_helpers import (
    consume_all_snapshots,
    default_reference_data,
    make_service,
    process_n_real_ticks,
    produce_ticks,
    seed_portfolios,
    unique_topics,
)


def _unpriceable_records(caplog):
    return [r for r in caplog.records if getattr(r, "event", None) == "portfolio_unpriceable"]


def test_empty_base_currency_is_refused_even_though_everything_else_is_priceable(
    kafka_stack, caplog
) -> None:
    """PF-1's positions have reference data, prices and curves once both its
    underlyings have ticked -- everything but its reporting currency is in
    place. With an empty `base_currency` it must still produce no snapshot,
    and be reported UNKNOWN_BASE_CURRENCY on every tick that affects it --
    including the first AAPL tick, where it would otherwise have been
    reported NO_PRICE (the currency check comes first). PF-2, USD, is
    unaffected."""
    caplog.set_level(logging.WARNING, logger="pricer")
    topics = unique_topics()

    portfolios = [
        dataclasses.replace(p, base_currency="") if p.portfolio_id == "PF-1" else p
        for p in load_portfolio_fixtures()
    ]
    seed_portfolios(kafka_stack, topics, portfolios)

    service = make_service(kafka_stack, topics, default_reference_data())
    service.hydrate()
    service.start_tick_consumption()

    scenario_id, ticks = load_tick_fixtures()
    produce_ticks(kafka_stack, topics, scenario_id, ticks)

    try:
        per_tick = process_n_real_ticks(service, len(ticks))
        produced = [snap for batch in per_tick for snap in batch]

        assert produced, "PF-2 must still be priced"
        assert all(s.portfolio_id == "PF-2" for s in produced)

        pf1_records = [r for r in _unpriceable_records(caplog) if r.portfolio_id == "PF-1"]
        assert pf1_records, "PF-1 must be reported, not silently skipped"
        for record in pf1_records:
            assert record.reason == UnpriceableReason.UNKNOWN_BASE_CURRENCY
            assert record.trigger == "tick"
            assert record.missing == ["PF-1"]
        assert service.unpriceable_counts[UnpriceableReason.UNKNOWN_BASE_CURRENCY] == len(
            pf1_records
        )
        assert service.unpriceable_counts[UnpriceableReason.NO_PRICE] == 0

        consumed = consume_all_snapshots(kafka_stack, topics, expected_count=len(produced))
        assert len(consumed) == len(produced)
        assert {s.portfolio_id for s in consumed} == {"PF-2"}
    finally:
        service.close()


def test_published_snapshots_carry_the_portfolios_base_currency(kafka_stack) -> None:
    """Asserted on the snapshots actually consumed from `risk.snapshots`,
    not on the pricer's internal state: both fixture portfolios are USD."""
    topics = unique_topics()
    seed_portfolios(kafka_stack, topics, load_portfolio_fixtures())

    service = make_service(kafka_stack, topics, default_reference_data())
    service.hydrate()
    service.start_tick_consumption()

    scenario_id, ticks = load_tick_fixtures()
    produce_ticks(kafka_stack, topics, scenario_id, ticks)

    try:
        per_tick = process_n_real_ticks(service, len(ticks))
        expected_count = sum(len(batch) for batch in per_tick)
        assert expected_count > 0

        consumed = consume_all_snapshots(kafka_stack, topics, expected_count=expected_count)
        assert len(consumed) == expected_count
        assert {s.portfolio_id for s in consumed} == {"PF-1", "PF-2"}
        assert {s.base_currency for s in consumed} == {"USD"}
    finally:
        service.close()
