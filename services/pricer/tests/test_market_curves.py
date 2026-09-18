"""ADR-0027: pricing options from `market.curves` -- hydration, live updates,
rejection reporting (`market_curve_rejected`, `rejected_curve_count`), and
the `MISSING_CURVE` unpriceable reason (and its precedence)."""
import logging
from decimal import Decimal

from loader import load_curve_fixtures, load_portfolio_fixtures, load_tick_fixtures
from meridian_contracts.market_curves import CurveKind, MarketCurve
from meridian_contracts.market_curves_key import CurveKind as KeyCurveKind
from meridian_contracts.market_curves_key import MarketCurveKey
from pricer.pricing import UnpriceableReason
from pricer.service import PricerService
from pricer_test_helpers import (
    default_reference_data,
    make_service,
    process_n_real_ticks,
    produce_raw_curve,
    produce_ticks,
    seed_curves,
    seed_portfolios,
    unique_topics,
)


def _unpriceable_records(caplog):
    return [r for r in caplog.records if getattr(r, "event", None) == "portfolio_unpriceable"]


def _rejected_records(caplog):
    return [r for r in caplog.records if getattr(r, "event", None) == "market_curve_rejected"]


def _default_curves_without(kind: CurveKind, curve_id: str) -> list[MarketCurve]:
    return [c for c in load_curve_fixtures() if not (c.kind == kind and c.curve_id == curve_id)]


def _run_fixture_ticks(kafka_stack, topics, service, portfolios=None):
    seed_portfolios(kafka_stack, topics, portfolios or load_portfolio_fixtures())
    service.hydrate()
    service.start_tick_consumption()
    scenario_id, ticks = load_tick_fixtures()
    produce_ticks(kafka_stack, topics, scenario_id, ticks)
    return process_n_real_ticks(service, len(ticks))


def test_missing_single_curve_reports_missing_curve_and_skips_only_that_portfolio(
    kafka_stack, caplog
) -> None:
    """(a) Default fixtures minus VOLATILITY MSFT: after the MSFT tick,
    PF-1 is reported MISSING_CURVE (trigger "tick", missing ==
    ["VOLATILITY:MSFT"]) and produces no snapshot on that tick; PF-2 (an
    equity-only portfolio, no curve requirement) still produces snapshots.
    This proves pricing no longer reads instruments.yaml's volatility,
    which still holds 0.35 for MSFT-PUT-280."""
    caplog.set_level(logging.WARNING, logger="pricer")
    topics = unique_topics()
    service = make_service(
        kafka_stack, topics, curves=_default_curves_without(CurveKind.VOLATILITY, "MSFT")
    )
    try:
        per_tick = _run_fixture_ticks(kafka_stack, topics, service)

        msft_tick_snapshots = per_tick[1]  # tick 2 is the MSFT tick
        assert all(s.portfolio_id != "PF-1" for s in msft_tick_snapshots)

        records = [
            r for r in _unpriceable_records(caplog) if r.portfolio_id == "PF-1" and r.trigger == "tick"
        ]
        assert len(records) >= 1
        assert records[-1].reason == UnpriceableReason.MISSING_CURVE
        assert records[-1].missing == ["VOLATILITY:MSFT"]

        pf2_snapshots = [s for batch in per_tick for s in batch if s.portfolio_id == "PF-2"]
        assert len(pf2_snapshots) == 2  # both AAPL ticks (1 and 3)
    finally:
        service.close()


def test_curves_seeded_under_different_scenario_id_report_all_five_missing(
    kafka_stack, caplog
) -> None:
    """(b) Curves seeded under a scenario_id other than the ticks'
    (ADR-0027 Decision 6: lookup is by the triggering tick's scenario_id):
    after the MSFT tick, PF-1 reports MISSING_CURVE with every one of its
    five required keys, sorted."""
    caplog.set_level(logging.WARNING, logger="pricer")
    topics = unique_topics()
    other_scenario_curves = [
        MarketCurve(
            scenario_id="other-scenario",
            kind=c.kind,
            curve_id=c.curve_id,
            value_float=c.value_float,
            value_decimal=c.value_decimal,
            event_time=c.event_time,
            ingest_time=c.ingest_time,
        )
        for c in load_curve_fixtures()
    ]
    service = make_service(kafka_stack, topics, curves=other_scenario_curves)
    try:
        _run_fixture_ticks(kafka_stack, topics, service)

        records = [
            r for r in _unpriceable_records(caplog) if r.portfolio_id == "PF-1" and r.trigger == "tick"
        ]
        assert len(records) >= 1
        assert records[-1].reason == UnpriceableReason.MISSING_CURVE
        assert records[-1].missing == sorted(
            [
                "RISK_FREE_RATE:USD",
                "VOLATILITY:AAPL",
                "DIVIDEND_YIELD:AAPL",
                "VOLATILITY:MSFT",
                "DIVIDEND_YIELD:MSFT",
            ]
        )
    finally:
        service.close()


def test_no_price_takes_precedence_over_missing_curve(kafka_stack, caplog) -> None:
    """(c) On the first AAPL tick (PF-1 hasn't seen an MSFT price yet), PF-1
    is reported NO_PRICE, not MISSING_CURVE, even though MSFT's volatility
    is also missing -- NO_PRICE precedes MISSING_CURVE (ADR-0027
    Decision 9)."""
    caplog.set_level(logging.WARNING, logger="pricer")
    topics = unique_topics()
    service = make_service(
        kafka_stack, topics, curves=_default_curves_without(CurveKind.VOLATILITY, "MSFT")
    )
    try:
        per_tick = _run_fixture_ticks(kafka_stack, topics, service)

        first_tick_records = [
            r
            for r in _unpriceable_records(caplog)
            if r.portfolio_id == "PF-1" and r.trigger == "tick"
        ]
        assert first_tick_records[0].reason == UnpriceableReason.NO_PRICE
        assert per_tick[0] == [] or all(s.portfolio_id != "PF-1" for s in per_tick[0])
    finally:
        service.close()


def test_rejection_at_hydration_removes_previous_value_and_counts(kafka_stack, caplog) -> None:
    """(d) Seed valid default curves, then a raw invalid record for
    VOLATILITY MSFT (value_decimal set, value_float null). After hydrate():
    exactly one market_curve_rejected record naming that key;
    rejected_curve_count == 1; after the MSFT tick, PF-1 reports
    MISSING_CURVE with ["VOLATILITY:MSFT"] -- the earlier valid value was
    removed, not kept (CurveView's supersede-on-invalid rule)."""
    caplog.set_level(logging.WARNING, logger="pricer")
    topics = unique_topics()
    service = make_service(kafka_stack, topics)  # seeds valid default curves

    invalid_key = MarketCurveKey(
        scenario_id="pricer-fixture-v1", kind=KeyCurveKind.VOLATILITY, curve_id="MSFT"
    )
    valid_msft_vol = next(
        c for c in load_curve_fixtures() if c.kind == CurveKind.VOLATILITY and c.curve_id == "MSFT"
    )
    invalid_value = MarketCurve(
        scenario_id="pricer-fixture-v1",
        kind=CurveKind.VOLATILITY,
        curve_id="MSFT",
        value_float=None,
        value_decimal=Decimal("0.35"),
        event_time=valid_msft_vol.event_time,
        ingest_time=valid_msft_vol.ingest_time,
    )
    produce_raw_curve(kafka_stack, topics, invalid_key, invalid_value)
    seed_portfolios(kafka_stack, topics, load_portfolio_fixtures())

    try:
        service.hydrate()

        rejected = _rejected_records(caplog)
        matching = [r for r in rejected if r.kind == "VOLATILITY" and r.curve_id == "MSFT"]
        assert len(matching) == 1
        assert service.rejected_curve_count == 1

        service.start_tick_consumption()
        scenario_id, ticks = load_tick_fixtures()
        produce_ticks(kafka_stack, topics, scenario_id, ticks)
        process_n_real_ticks(service, len(ticks))

        records = [
            r for r in _unpriceable_records(caplog) if r.portfolio_id == "PF-1" and r.trigger == "tick"
        ]
        assert records[-1].reason == UnpriceableReason.MISSING_CURVE
        assert records[-1].missing == ["VOLATILITY:MSFT"]
    finally:
        service.close()


def test_key_value_curve_id_mismatch_is_rejected(kafka_stack, caplog) -> None:
    """(e) A raw record whose key curve_id is MSFT and value curve_id is
    AAPL is rejected with a market_curve_rejected record."""
    caplog.set_level(logging.WARNING, logger="pricer")
    topics = unique_topics()
    service = make_service(kafka_stack, topics, curves=[])

    aapl_vol = next(
        c for c in load_curve_fixtures() if c.kind == CurveKind.VOLATILITY and c.curve_id == "AAPL"
    )
    mismatched_key = MarketCurveKey(
        scenario_id="pricer-fixture-v1", kind=KeyCurveKind.VOLATILITY, curve_id="MSFT"
    )
    mismatched_value = MarketCurve(
        scenario_id="pricer-fixture-v1",
        kind=CurveKind.VOLATILITY,
        curve_id="AAPL",
        value_float=aapl_vol.value_float,
        value_decimal=None,
        event_time=aapl_vol.event_time,
        ingest_time=aapl_vol.ingest_time,
    )
    produce_raw_curve(kafka_stack, topics, mismatched_key, mismatched_value)
    seed_portfolios(kafka_stack, topics, load_portfolio_fixtures())

    try:
        service.hydrate()
        rejected = _rejected_records(caplog)
        matching = [r for r in rejected if r.kind == "VOLATILITY" and r.curve_id == "MSFT"]
        assert len(matching) == 1
        assert service.rejected_curve_count == 1
    finally:
        service.close()


def test_live_curve_update_before_ticks_prices_pf1_on_msft_tick(kafka_stack) -> None:
    """(f) Start with MSFT's vol missing, hydrate, start tick consumption,
    then publish VOLATILITY MSFT 0.35 with a MarketCurveProducer, then
    produce the fixture ticks; PF-1 is priced on the MSFT tick. Uses
    process_n_real_ticks; no sleeps."""
    topics = unique_topics()
    service = make_service(
        kafka_stack, topics, curves=_default_curves_without(CurveKind.VOLATILITY, "MSFT")
    )
    try:
        seed_portfolios(kafka_stack, topics, load_portfolio_fixtures())
        service.hydrate()
        service.start_tick_consumption()

        msft_vol = next(
            c
            for c in load_curve_fixtures()
            if c.kind == CurveKind.VOLATILITY and c.curve_id == "MSFT"
        )
        seed_curves(kafka_stack, topics, [msft_vol])

        scenario_id, ticks = load_tick_fixtures()
        produce_ticks(kafka_stack, topics, scenario_id, ticks)
        per_tick = process_n_real_ticks(service, len(ticks))

        msft_tick_snapshots = per_tick[1]
        assert any(s.portfolio_id == "PF-1" for s in msft_tick_snapshots)
    finally:
        service.close()


def test_hydration_timeout_names_the_topic(kafka_stack) -> None:
    """(g) A market_curve_topic that was never created (bypassing
    make_service's seeding for this one test) causes hydrate() to time out
    -- confirmed by this session's experiment: the subscribed topic not
    existing means poll() never raises and on_assign never fires, so no
    partitions are ever assigned; the TimeoutError names the topic and says
    so explicitly."""
    topics = unique_topics()
    never_created_topic = topics.market_curves  # never seeded/created

    # portfolio.state must exist (be created) so its own hydration phase
    # succeeds and we reach market.curves hydration -- otherwise the
    # timeout observed would be portfolio.state's, not market.curves'.
    seed_portfolios(kafka_stack, topics, load_portfolio_fixtures())

    service = PricerService(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        reference_data=default_reference_data(),
        tick_group_id="test-hydration-timeout",
        portfolio_state_topic=topics.portfolio_state,
        tick_topic=topics.market_ticks,
        risk_snapshot_topic=topics.risk_snapshots,
        market_curve_topic=never_created_topic,
    )
    try:
        try:
            service.hydrate(timeout=5)
        except TimeoutError as exc:
            message = str(exc)
            assert never_created_topic in message
            assert "no partitions were assigned" in message
        else:
            raise AssertionError("expected hydrate() to time out")
    finally:
        service.close()
