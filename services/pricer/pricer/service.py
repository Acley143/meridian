"""Orchestrates hydration, tick-driven repricing, and snapshot production.

Startup sequence (Task 1): `hydrate()` blocks, consuming `portfolio.state`
to the end of every assigned partition, before `start_tick_consumption()`
ever subscribes to `market.ticks`. Nothing in this class touches the tick
topic until hydration is complete -- a tick "arriving" before then is not
buffered or specially handled, it simply isn't fetched yet, because the
consumer group for it doesn't exist yet. This is the "paused" strategy
Task 1 allows, chosen over in-memory buffering because it can't leak: there
is no buffer to overflow or lose on a crash between hydration and the first
tick.

Per-tick flow (Tasks 3, 5, 6, 7): update the last-known price/event_time for
the ticked instrument, find every portfolio holding it (the reverse index,
keyed by underlying_id -- see `pricer.portfolio_view`), price and aggregate
each one (one snapshot per affected portfolio, Task 6's Q1 fan-out policy),
flush all of them to the broker, and only then commit the tick's offset --
never before every snapshot it produced is durably delivered.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from decimal import Decimal
from logging import Logger

from meridian_contracts.risk_snapshot import RiskSnapshot
from meridian_contracts.tick import Tick
from quant_core import PRICER_VERSION
from quant_io.clock import now_utc
from quant_io.consumer import PartitionEOF
from quant_io.portfolio_state_io import (
    PORTFOLIO_STATE_TOPIC,
    make_portfolio_state_consumer,
)
from quant_io.risk_snapshot_io import RISK_SNAPSHOTS_TOPIC, RiskSnapshotProducer
from quant_io.tick_producer import MARKET_TICKS_TOPIC, make_tick_consumer

from pricer.logging_config import get_logger
from pricer.portfolio_view import PortfolioView
from pricer.pricing import (
    UnpricableInstrumentError,
    aggregate_portfolio,
    aggregate_position,
    oldest_input_event_time,
    price_instrument,
)
from pricer.reference_data import ReferenceData

_DEFAULT_HYDRATION_TIMEOUT_SECONDS = 30.0


class PricerService:
    def __init__(
        self,
        *,
        bootstrap_servers: str,
        schema_registry_url: str,
        reference_data: ReferenceData,
        tick_group_id: str,
        portfolio_state_topic: str = PORTFOLIO_STATE_TOPIC,
        tick_topic: str = MARKET_TICKS_TOPIC,
        risk_snapshot_topic: str = RISK_SNAPSHOTS_TOPIC,
        logger: Logger | None = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._schema_registry_url = schema_registry_url
        self.reference_data = reference_data
        self._tick_group_id = tick_group_id
        self._portfolio_state_topic = portfolio_state_topic
        self._tick_topic = tick_topic
        self._log = logger or get_logger()

        self.view = PortfolioView(reference_data)
        self._last_price: dict[str, Decimal] = {}
        self._last_event_time: dict[str, datetime] = {}
        self.ready = False

        self._portfolio_consumer = None
        self._tick_consumer = None
        self._risk_producer = RiskSnapshotProducer(
            bootstrap_servers=bootstrap_servers,
            schema_registry_url=schema_registry_url,
            topic=risk_snapshot_topic,
        )

    # -- Task 1: hydration gate ------------------------------------------

    def hydrate(self, timeout: float = _DEFAULT_HYDRATION_TIMEOUT_SECONDS) -> None:
        """Block until `portfolio.state` has been read to the end of every
        assigned partition. Must be called before `start_tick_consumption`."""
        state: dict[str, object] = {"assigned": False, "pending": set()}

        def on_assign(_consumer: object, partitions: list) -> None:
            state["pending"] = {(p.topic, p.partition) for p in partitions}
            state["assigned"] = True
            self._log.info(
                "hydration: assigned %d partition(s) of portfolio.state", len(partitions)
            )

        self._log.info("hydration: starting (readiness=HYDRATING)")
        # A fresh group id every hydration run: the local view is rebuilt
        # from scratch each start (ADR-0003 -- "a new pricer instance can
        # rebuild its view by replaying the topic from the start"), never
        # resumed from a previously committed offset.
        self._portfolio_consumer = make_portfolio_state_consumer(
            bootstrap_servers=self._bootstrap_servers,
            schema_registry_url=self._schema_registry_url,
            group_id=f"pricer-portfolio-view-{uuid.uuid4()}",
            topic=self._portfolio_state_topic,
            enable_partition_eof=True,
            on_assign=on_assign,
        )

        deadline = time.monotonic() + timeout
        while not (state["assigned"] and not state["pending"]):
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"portfolio.state hydration did not complete within {timeout}s "
                    f"(still pending: {state['pending']})"
                )
            msg = self._portfolio_consumer.poll(1.0)
            if isinstance(msg, PartitionEOF):
                state["pending"].discard((msg.topic, msg.partition))
            elif msg is not None:
                self._apply_portfolio_message(msg)

        self.ready = True
        self._log.info(
            "hydration: complete (readiness=READY), %d portfolio(s) in view", len(self.view)
        )

    def _apply_portfolio_message(self, msg: object) -> None:
        key = msg.key()
        value = msg.value()
        if value is None:
            removed = self.view.remove(key.portfolio_id)
            self._log.info("portfolio.state tombstone: portfolio_id=%s removed=%s", key.portfolio_id, removed)
        else:
            self.view.apply(key.portfolio_id, value.positions, value.event_time)
            self._log.info(
                "portfolio.state applied: portfolio_id=%s positions=%d",
                key.portfolio_id,
                len(value.positions),
            )
        self._portfolio_consumer.commit(msg)

    def _drain_portfolio_updates(self) -> None:
        while True:
            msg = self._portfolio_consumer.poll(0.0)
            if msg is None or isinstance(msg, PartitionEOF):
                return
            self._apply_portfolio_message(msg)

    # -- Tasks 3/5/6/7: tick-driven repricing ----------------------------

    def start_tick_consumption(self) -> None:
        if not self.ready:
            raise RuntimeError("start_tick_consumption called before hydrate() completed")
        self._tick_consumer = make_tick_consumer(
            bootstrap_servers=self._bootstrap_servers,
            schema_registry_url=self._schema_registry_url,
            group_id=self._tick_group_id,
            topic=self._tick_topic,
        )
        self._log.info("tick consumption started: group_id=%s", self._tick_group_id)

    def process_one_tick(self, timeout: float = 5.0) -> list[RiskSnapshot] | None:
        """Poll for one tick and, if one arrives within `timeout`, reprice
        every affected portfolio and produce a snapshot for each. Returns
        `None` on a poll timeout (no tick arrived), else the list of
        snapshots produced for that tick (possibly empty, if every
        affected portfolio was unpricable)."""
        if self._tick_consumer is None:
            raise RuntimeError("start_tick_consumption() was not called")

        self._drain_portfolio_updates()

        msg = self._tick_consumer.poll(timeout)
        if msg is None or isinstance(msg, PartitionEOF):
            return None

        tick: Tick = msg.value()
        self._last_price[tick.instrument_id] = tick.price
        self._last_event_time[tick.instrument_id] = tick.event_time

        affected = self.view.portfolios_for_underlying(tick.instrument_id)
        produced: list[RiskSnapshot] = []
        for portfolio_id in sorted(affected):
            snapshot = self._price_portfolio(portfolio_id, tick)
            if snapshot is not None:
                self._risk_producer.produce_snapshot(snapshot)
                produced.append(snapshot)

        # Flush (durably deliver) every snapshot this tick produced before
        # committing the tick's own offset (Task 7) -- never the reverse.
        self._risk_producer.flush()
        self._tick_consumer.commit(msg)

        self._log.info(
            "tick processed: instrument_id=%s affected=%d snapshots=%d",
            tick.instrument_id,
            len(affected),
            len(produced),
        )
        return produced

    def _price_portfolio(self, portfolio_id: str, triggering_tick: Tick) -> RiskSnapshot | None:
        positions = self.view.positions(portfolio_id)
        contributions = []
        underlyings_used: set[str] = set()

        for position in positions:
            if position.instrument_id not in self.reference_data:
                self._log.warning(
                    "skipping portfolio_id=%s: no reference data for instrument_id=%s",
                    portfolio_id,
                    position.instrument_id,
                )
                return None
            reference = self.reference_data.get(position.instrument_id)
            underlying_id = reference.underlying_id
            if underlying_id not in self._last_price:
                self._log.warning(
                    "skipping portfolio_id=%s: no observed price yet for underlying_id=%s",
                    portfolio_id,
                    underlying_id,
                )
                return None

            spot = self._last_price[underlying_id]
            try:
                pricing_result = price_instrument(reference, spot, triggering_tick.event_time)
            except UnpricableInstrumentError as exc:
                self._log.warning("skipping portfolio_id=%s: %s", portfolio_id, exc)
                return None

            contributions.append(
                aggregate_position(pricing_result, position.quantity, reference.contract_size, spot)
            )
            underlyings_used.add(underlying_id)

        aggregate = aggregate_portfolio(contributions)
        oldest = oldest_input_event_time(underlyings_used, self._last_event_time)

        return RiskSnapshot(
            portfolio_id=portfolio_id,
            as_of=triggering_tick.event_time,
            pricer_version=PRICER_VERSION,
            price=aggregate.price,
            cash_delta=aggregate.cash_delta,
            cash_gamma=aggregate.cash_gamma,
            cash_vega=aggregate.cash_vega,
            cash_theta=aggregate.cash_theta,
            cash_rho=aggregate.cash_rho,
            var_95=0.0,
            scenario_id=triggering_tick.scenario_id,
            oldest_input_event_time=oldest,
            ingest_time=now_utc(),
        )

    def run(self) -> None:
        self.hydrate()
        self.start_tick_consumption()
        while True:
            self.process_one_tick()

    def close(self) -> None:
        if self._portfolio_consumer is not None:
            self._portfolio_consumer.close()
        if self._tick_consumer is not None:
            self._tick_consumer.close()
