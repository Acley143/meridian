"""The `portfolio.state` producer/consumer (ADR-0003, ADR-0016: keyed by
`portfolio_id`).

The producer side exists for `services/pricer/fixtures` -- `core-service`
doesn't exist yet (ADR-0003 is designed for exactly this: the pricer
consumes a contract, not a service, and doesn't care what wrote it), so
tests need a way to seed the topic directly, tombstones included.
"""
from __future__ import annotations

from meridian_contracts import portfolio_state as portfolio_state_schema
from meridian_contracts import portfolio_state_key as portfolio_state_key_schema
from meridian_contracts.portfolio_state import PortfolioState
from meridian_contracts.portfolio_state_key import PortfolioStateKey

from quant_io.consumer import AvroConsumer, OnAssign
from quant_io.producer import AvroProducer

PORTFOLIO_STATE_TOPIC = "portfolio.state"


class PortfolioStateProducer:
    """Produces `PortfolioState` messages to `portfolio.state`, keyed by
    `portfolio_id`. `produce_tombstone` publishes the deletion convention
    (contracts/README.md, docs/domain-model.md#portfoliostate): a null
    value for the portfolio's key."""

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        schema_registry_url: str,
        topic: str = PORTFOLIO_STATE_TOPIC,
        max_queue_size: int = 10_000,
    ) -> None:
        self._producer = AvroProducer(
            bootstrap_servers=bootstrap_servers,
            schema_registry_url=schema_registry_url,
            topic=topic,
            value_schema_str=portfolio_state_schema.SCHEMA_JSON,
            value_to_dict=PortfolioState.to_dict,
            key_schema_str=portfolio_state_key_schema.SCHEMA_JSON,
            key_to_dict=PortfolioStateKey.to_dict,
            max_queue_size=max_queue_size,
        )

    def produce_state(self, state: PortfolioState) -> None:
        self._producer.produce(key=PortfolioStateKey(portfolio_id=state.portfolio_id), value=state)

    def produce_tombstone(self, portfolio_id: str) -> None:
        self._producer.produce(key=PortfolioStateKey(portfolio_id=portfolio_id), value=None)

    def flush(self, timeout: float = 30.0) -> int:
        return self._producer.flush(timeout)


def make_portfolio_state_consumer(
    *,
    bootstrap_servers: str,
    schema_registry_url: str,
    group_id: str,
    topic: str = PORTFOLIO_STATE_TOPIC,
    enable_partition_eof: bool = False,
    on_assign: OnAssign | None = None,
) -> AvroConsumer:
    return AvroConsumer(
        bootstrap_servers=bootstrap_servers,
        schema_registry_url=schema_registry_url,
        topic=topic,
        group_id=group_id,
        value_schema_str=portfolio_state_schema.SCHEMA_JSON,
        value_from_dict=PortfolioState.from_dict,
        key_schema_str=portfolio_state_key_schema.SCHEMA_JSON,
        key_from_dict=PortfolioStateKey.from_dict,
        enable_partition_eof=enable_partition_eof,
        on_assign=on_assign,
    )
