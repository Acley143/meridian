"""ADR-0032: invalid inputs and failed model evaluations are reported, never
allowed to stop the tick loop.

Decision 1: a tick whose price is not strictly positive is rejected at
consume, exactly as ADR-0028 Decision 7 rejects a tick in the wrong currency
-- logged, counted, the offset committed, and the price never cached.

Decision 2: a quant-core input-validation failure (here, an option held past
its expiry) is that position's failure, reported INSTRUMENT_NOT_PRICEABLE,
and the other portfolios on the same tick are still priced (Decision 5).

Decision 3: a ValueError from the VaR statistic makes the portfolio
INSTRUMENT_NOT_PRICEABLE. No Kafka input reaches it, so its test puts an
unvalidated curve into the view directly.

Everything runs against the shared fixtures: `instruments.yaml`
(AAPL-CALL-150 expires 2026-06-01T00:00:00Z) and `curves.yaml` under
`pricer-fixture-v1`.
"""
import dataclasses
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from loader import PortfolioFixture, TickFixture, load_curve_fixtures
from meridian_contracts.market_curves import CurveKind
from meridian_contracts.portfolio_state import Position
from pricer.pricing import UnpriceableReason
from pricer_test_helpers import (
    make_service,
    process_n_real_ticks,
    produce_ticks,
    seed_portfolios,
    unique_topics,
)
from quant_io.consumer import PartitionEOF

_SCENARIO = "pricer-fixture-v1"
_T0 = datetime(2026, 1, 2, 9, 30, 0, tzinfo=UTC)


def _at(seconds: int) -> datetime:
    return datetime(2026, 1, 2, 9, 30, seconds, tzinfo=UTC)


def _portfolio(portfolio_id: str, instrument_id: str, quantity: str) -> PortfolioFixture:
    return PortfolioFixture(
        portfolio_id=portfolio_id,
        base_currency="USD",
        positions=[
            Position(
                portfolio_id=portfolio_id,
                instrument_id=instrument_id,
                quantity=Decimal(quantity),
                average_cost=Decimal(1),
                as_of_event_time=_T0,
            )
        ],
        event_time=_T0,
    )


def _unpriceable_records(caplog):
    return [r for r in caplog.records if getattr(r, "event", None) == "portfolio_unpriceable"]


def _price_rejections(caplog):
    return [r for r in caplog.records if getattr(r, "event", None) == "tick_price_not_positive"]


def _start(kafka_stack, portfolios, tick_group_id=None):
    """Seed, hydrate and subscribe. Returns `(service, topics)`; the caller
    produces ticks and closes the service.

    Everything is seeded before `hydrate()`, so the hydration gate alone must
    put it in the views (ADR-0018); no post-hydration wait applies (ADR-0030
    Decision 6). The gate is asserted rather than assumed, so a gate failure
    is reported as one instead of as an empty affected-portfolio set."""
    topics = unique_topics()
    curves = load_curve_fixtures()
    seed_portfolios(kafka_stack, topics, portfolios)
    service = make_service(kafka_stack, topics, tick_group_id=tick_group_id, curves=curves)
    service.hydrate()
    missing = sorted({p.portfolio_id for p in portfolios} - service.view.portfolio_ids())
    missing += [
        f"curve {c.scenario_id}/{c.kind.value}/{c.curve_id}"
        for c in curves
        if service.curves.get(c.scenario_id, c.kind, c.curve_id) is None
    ]
    assert not missing, f"hydration gate did not hold: {missing}"
    service.start_tick_consumption()
    return service, topics


def test_zero_price_tick_on_an_option_underlying_is_rejected_and_the_loop_survives(
    kafka_stack, caplog
) -> None:
    """T1. P holds only AAPL-CALL-150.
      t=0 AAPL 150.00  good     -> one snapshot
      t=1 AAPL   0     REJECTED: logged, counted, no snapshot, no
                                 INSTRUMENT_NOT_PRICEABLE, cached price and
                                 event time still t=0's
      t=2 AAPL 151.00  good     -> one snapshot: the loop survived
    Unfixed, MarketState rejects spot 0 with a ValueError that escapes
    process_one_tick."""
    caplog.set_level(logging.WARNING, logger="pricer")
    service, topics = _start(kafka_stack, [_portfolio("P", "AAPL-CALL-150", "10")])
    try:
        produce_ticks(
            kafka_stack,
            topics,
            _SCENARIO,
            [
                TickFixture("AAPL", Decimal("150.00"), "USD", _at(0)),
                TickFixture("AAPL", Decimal(0), "USD", _at(1)),
                TickFixture("AAPL", Decimal("151.00"), "USD", _at(2)),
            ],
        )

        first, rejected = process_n_real_ticks(service, 2)
        assert [s.portfolio_id for s in first] == ["P"]
        assert rejected == [], "a rejected tick produces no snapshot"
        assert service._last_price["AAPL"] == Decimal("150.00")
        assert service._last_event_time["AAPL"] == _at(0)

        records = _price_rejections(caplog)
        assert len(records) == 1
        assert records[0].instrument_id == "AAPL"
        assert records[0].price == Decimal(0)
        assert service.tick_price_not_positive_count == 1
        assert _unpriceable_records(caplog) == []
        assert service.unpriceable_counts[UnpriceableReason.INSTRUMENT_NOT_PRICEABLE] == 0

        (after,) = process_n_real_ticks(service, 1)
        assert [s.portfolio_id for s in after] == ["P"], "the loop survived"
        assert after[0].as_of == _at(2)
    finally:
        service.close()


@pytest.mark.parametrize("bad_price", ["0", "-150.00"])
def test_non_positive_price_tick_on_an_equity_produces_no_snapshot(
    kafka_stack, caplog, bad_price
) -> None:
    """T2. P holds only AAPL equity, which is priced without validation, so
    unfixed this publishes a snapshot priced at zero or below -- the
    wrong-number failure. Fixed, the tick is rejected and nothing is
    published. A valid tick afterwards must be priced, so an empty view
    cannot pass this test."""
    caplog.set_level(logging.WARNING, logger="pricer")
    service, topics = _start(kafka_stack, [_portfolio("P", "AAPL", "1000")])
    try:
        produce_ticks(
            kafka_stack,
            topics,
            _SCENARIO,
            [
                TickFixture("AAPL", Decimal(bad_price), "USD", _at(0)),
                TickFixture("AAPL", Decimal("150.00"), "USD", _at(1)),
            ],
        )
        (produced,) = process_n_real_ticks(service, 1)
        assert produced == [], f"a {bad_price} tick must not be priced"
        assert "AAPL" not in service._last_price
        assert len(_price_rejections(caplog)) == 1
        assert service.tick_price_not_positive_count == 1

        (after,) = process_n_real_ticks(service, 1)
        assert [s.portfolio_id for s in after] == ["P"], "a valid tick after the rejection is priced"
    finally:
        service.close()


def test_expired_option_is_not_priceable_and_does_not_stop_other_portfolios(
    kafka_stack, caplog
) -> None:
    """T3. PF-A (sorts first) holds only AAPL-CALL-150, which expired
    2026-06-01; PF-B holds only AAPL equity. One AAPL tick at 2026-07-01:
    PF-A is reported INSTRUMENT_NOT_PRICEABLE naming the option, with the
    expiry failure in the detail, PF-B is still priced, and the tick's offset
    is committed.

    The commit is asserted the way `test_restart.py` asserts redelivery: a
    second service on the same stable tick group id resumes from the last
    committed offset, so its first real tick must be the sentinel produced
    after the expired one, not the expired one again. Unfixed, the expiry
    ValueError escapes process_one_tick before any of this."""
    caplog.set_level(logging.WARNING, logger="pricer")
    stable_tick_group_id = f"invalid-inputs-{uuid.uuid4()}"
    expired_at = datetime(2026, 7, 1, tzinfo=UTC)
    sentinel_at = datetime(2026, 7, 1, 0, 0, 1, tzinfo=UTC)
    portfolios = [_portfolio("PF-A", "AAPL-CALL-150", "10"), _portfolio("PF-B", "AAPL", "1000")]

    service_a, topics = _start(kafka_stack, portfolios, tick_group_id=stable_tick_group_id)
    try:
        produce_ticks(
            kafka_stack,
            topics,
            _SCENARIO,
            [
                TickFixture("AAPL", Decimal("150.00"), "USD", expired_at),
                TickFixture("MSFT", Decimal("200.00"), "USD", sentinel_at),
            ],
        )
        (produced,) = process_n_real_ticks(service_a, 1)
        assert [s.portfolio_id for s in produced] == ["PF-B"]

        records = [r for r in _unpriceable_records(caplog) if r.portfolio_id == "PF-A"]
        assert len(records) == 1
        record = records[0]
        assert record.reason == UnpriceableReason.INSTRUMENT_NOT_PRICEABLE
        assert record.trigger == "tick"
        assert record.missing == ["AAPL-CALL-150"]
        assert "expiry" in record.detail
        assert service_a.unpriceable_counts[UnpriceableReason.INSTRUMENT_NOT_PRICEABLE] == 1
    finally:
        service_a.close()

    service_b = make_service(kafka_stack, topics, tick_group_id=stable_tick_group_id)
    try:
        service_b.hydrate()
        service_b.start_tick_consumption()
        msg = None
        for _ in range(10):
            msg = service_b._tick_consumer.poll(5.0)
            if msg is not None and not isinstance(msg, PartitionEOF):
                break
        assert msg is not None, "expected the sentinel tick to be delivered"
        resumed = msg.value()
        assert (resumed.instrument_id, resumed.event_time) == ("MSFT", sentinel_at), (
            "the expired tick was redelivered, so its offset was not committed"
        )
    finally:
        service_b.close()


def test_a_var_failure_is_not_priceable_and_produces_no_snapshot(kafka_stack, caplog) -> None:
    """T5. ADR-0032 Decision 3, defence in depth. Seam: the hydrated
    `CurveView`'s own mapping. A negative VOLATILITY can no longer arrive
    through Kafka -- `validate_market_curve` rejects it at the producer and
    again in `CurveView.apply` -- so this puts one into the view "another
    way", the case the PLAN's open question names, and everything from
    `process_one_tick` down (curve lookup, equity pricing, the VaR call and
    its catch) runs unmodified. An equity is used because, unlike an option,
    nothing before the VaR statistic validates its volatility."""
    caplog.set_level(logging.WARNING, logger="pricer")
    service, topics = _start(kafka_stack, [_portfolio("P", "AAPL", "1000")])
    try:
        key = (_SCENARIO, CurveKind.VOLATILITY, "AAPL")
        service.curves._curves[key] = dataclasses.replace(
            service.curves._curves[key], value_float=-0.25
        )
        produce_ticks(
            kafka_stack, topics, _SCENARIO, [TickFixture("AAPL", Decimal("150.00"), "USD", _at(0))]
        )
        (produced,) = process_n_real_ticks(service, 1)
        assert produced == []

        records = [r for r in _unpriceable_records(caplog) if r.portfolio_id == "P"]
        assert len(records) == 1
        record = records[0]
        assert record.reason == UnpriceableReason.INSTRUMENT_NOT_PRICEABLE
        assert record.missing == ["AAPL"]
        assert record.detail == (
            "portfolio VaR could not be computed: annual_volatility must be non-negative, got -0.25"
        )
    finally:
        service.close()
