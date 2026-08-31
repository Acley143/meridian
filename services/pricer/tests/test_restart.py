"""Task 9: kill mid-stream, restart, assert no gaps and duplicate
identities are safe (ADR-0007, Task 7).

The crash is simulated at the point that actually matters: a snapshot was
already produced and flushed (durably delivered) for a tick, but the
tick's own offset was never committed -- exactly what a hard process kill
between `flush()` and `commit()` looks like. A restart with the same
(stable) tick consumer group id must redeliver that tick, safely producing
a duplicate snapshot identity rather than either losing it or corrupting
anything.

**Known gap, discovered by this test, not papered over:** `PortfolioView`
fully rehydrates from `portfolio.state` on every restart (ADR-0003 -- the
whole point of a log-compacted topic is that it can be replayed from
scratch). The tick-derived last-known-price cache (`PricerService.
_last_price`/`_last_event_time`) has no equivalent recovery: it is
in-memory only, built solely from ticks consumed *after* the last commit.
A restarted pricer redelivering a tick that affects a *multi-underlying*
portfolio can find itself missing the price for that portfolio's other
underlying(s) -- ticks it saw before the crash but whose consumption was
already committed, so they are never redelivered. The portfolio then
silently stops producing snapshots until every one of its underlyings has
ticked again post-restart. This test exercises the case that *is* safe
today (a redelivered tick whose affected portfolio needs no other
underlying's price); `test_price_cache_does_not_survive_restart` below
characterizes the gap directly. See `services/pricer/PLAN.md`'s open
questions.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from loader import PortfolioFixture, load_portfolio_fixtures, load_tick_fixtures
from meridian_contracts.portfolio_state import Position
from meridian_contracts.tick import Tick
from pricer_test_helpers import (
    default_reference_data,
    make_service,
    process_n_real_ticks,
    produce_ticks,
    seed_portfolios,
    unique_topics,
)
from quant_io.consumer import PartitionEOF
from quant_io.tick_producer import TickProducer


def test_restart_no_gaps_and_duplicates_are_safe(kafka_stack) -> None:
    topics = unique_topics()
    reference_data = default_reference_data()
    # PF-2 only: single-underlying (AAPL), so a redelivered AAPL tick needs
    # no other underlying's cached price -- isolates "is redelivery safe"
    # from the price-cache-recovery gap documented above.
    seed_portfolios(kafka_stack, topics, load_portfolio_fixtures())
    scenario_id, ticks = load_tick_fixtures()
    stable_tick_group_id = f"restart-test-{uuid.uuid4()}"

    service_a = make_service(kafka_stack, topics, reference_data, tick_group_id=stable_tick_group_id)
    service_a.hydrate()
    service_a.start_tick_consumption()

    produce_ticks(kafka_stack, topics, scenario_id, ticks)

    # Tick 1 (AAPL): price it and durably produce PF-2's snapshot (its only
    # affected portfolio at this point -- PF-1 needs MSFT too, unseen yet),
    # matching what process_one_tick does up to and including flush() --
    # then simulate the crash by never calling commit().
    msg = None
    for _ in range(10):
        msg = service_a._tick_consumer.poll(5.0)
        if msg is not None and not isinstance(msg, PartitionEOF):
            break
    assert msg is not None, "expected the first tick to be available"
    tick = msg.value()
    assert tick.instrument_id == "AAPL"

    service_a._last_price[tick.instrument_id] = tick.price
    service_a._last_event_time[tick.instrument_id] = tick.event_time

    pre_crash_snapshots = []
    for portfolio_id in sorted(service_a.view.portfolios_for_underlying(tick.instrument_id)):
        snapshot = service_a._price_portfolio(portfolio_id, tick)
        if snapshot is not None:
            service_a._risk_producer.produce_snapshot(snapshot)
            pre_crash_snapshots.append(snapshot)
    service_a._risk_producer.flush()
    assert len(pre_crash_snapshots) == 1
    assert pre_crash_snapshots[0].portfolio_id == "PF-2"
    # No commit() call here -- this is the crash. Close the consumer
    # (without committing -- enable.auto.commit is False) so it actually
    # leaves the group; a real process kill wouldn't call close() at all,
    # but leaving this one as a live, still-uncommitted group member would
    # contend with service_b for the same partition instead of simulating
    # "the old process is gone."
    service_a.close()

    # "Restart": a fresh service instance. Same stable tick group id, so it
    # resumes from the last *committed* offset (nothing was committed yet,
    # so tick 1 is redelivered from the start). A fresh, unique
    # portfolio-view group id, so the view rehydrates from scratch
    # (ADR-0003), independent of anything service_a did.
    service_b = make_service(kafka_stack, topics, reference_data, tick_group_id=stable_tick_group_id)
    service_b.hydrate()
    assert service_b.view.portfolio_ids() == service_a.view.portfolio_ids()
    service_b.start_tick_consumption()

    processed_b = process_n_real_ticks(service_b, 1)
    assert [len(batch) for batch in processed_b] == [1]
    redelivered_snapshots = processed_b[0]

    def identity(snapshot):
        return (snapshot.portfolio_id, snapshot.as_of, snapshot.pricer_version)

    # No gap: the redelivered tick produces exactly the same identity as
    # the pre-crash attempt. A duplicate delivery of the same identity is
    # exactly what ADR-0007's idempotent upsert exists to make safe.
    assert {identity(s) for s in redelivered_snapshots} == {identity(s) for s in pre_crash_snapshots}

    service_b.close()


def test_price_cache_does_not_survive_restart(kafka_stack) -> None:
    """Characterizes the gap described in this module's docstring: after a
    restart, a portfolio needing a price the new process hasn't observed
    yet (because the tick that carried it was already committed, so it's
    never redelivered) does not produce a snapshot, even though the
    portfolio view itself is fully and correctly rehydrated.

    This is not the desired end state -- it's a real limitation, tracked in
    `services/pricer/PLAN.md`'s open questions. This test exists so a
    future fix changes an assertion here on purpose, rather than the gap
    being rediscovered by surprise.
    """
    topics = unique_topics()
    reference_data = default_reference_data()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    portfolio = PortfolioFixture(
        portfolio_id="MULTI",
        positions=[
            Position(
                portfolio_id="MULTI",
                instrument_id="AAPL-CALL-150",
                quantity=Decimal(1),
                average_cost=Decimal(1),
                as_of_event_time=t0,
            ),
            Position(
                portfolio_id="MULTI",
                instrument_id="MSFT-PUT-280",
                quantity=Decimal(1),
                average_cost=Decimal(1),
                as_of_event_time=t0,
            ),
        ],
        event_time=t0,
    )
    seed_portfolios(kafka_stack, topics, [portfolio])
    stable_tick_group_id = f"restart-gap-{uuid.uuid4()}"

    service_a = make_service(kafka_stack, topics, reference_data, tick_group_id=stable_tick_group_id)
    service_a.hydrate()
    service_a.start_tick_consumption()

    tick_producer = TickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topics.market_ticks,
    )

    def send(instrument_id: str, price: str, event_time: datetime) -> None:
        tick_producer.produce_tick(
            Tick(
                instrument_id=instrument_id,
                price=Decimal(price),
                currency="USD",
                event_time=event_time,
                ingest_time=event_time,
                scenario_id="s",
            )
        )
        tick_producer.flush()

    # AAPL ticks first (committed normally); MSFT never ticks before the
    # "restart." MULTI can't be priced yet (missing MSFT) -- expected.
    send("AAPL", "150.00", datetime(2026, 1, 2, tzinfo=UTC))
    first = process_n_real_ticks(service_a, 1)
    assert first[0] == []
    service_a.close()

    # Restart: fresh price cache. Now MSFT ticks for the first time.
    service_b = make_service(kafka_stack, topics, reference_data, tick_group_id=stable_tick_group_id)
    service_b.hydrate()
    service_b.start_tick_consumption()

    send("MSFT", "200.00", datetime(2026, 1, 3, tzinfo=UTC))
    second = process_n_real_ticks(service_b, 1)

    # The gap: MULTI still can't be priced, even though AAPL *was* observed
    # (by service_a, pre-restart) -- service_b has no way to know that.
    assert second[0] == [], (
        "if this now produces a snapshot, the price-cache-recovery gap "
        "this test documents has been fixed -- update this test and its "
        "docstring, and close the PLAN.md open question"
    )

    service_b.close()
