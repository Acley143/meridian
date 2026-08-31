"""Round-trip tests (Python side): serialize, deserialize, assert equality
across every field, for every generated record type. Companion to
contracts/generated/java/src/test/java/com/meridian/contracts/RoundTripTest.java
-- same principle, other language.
"""
import io
from datetime import datetime, timezone
from decimal import Decimal

import avro.io
import avro.schema
from meridian_contracts.portfolio_state import (
    SCHEMA_JSON as PORTFOLIO_STATE_SCHEMA_JSON,
)
from meridian_contracts.portfolio_state import PortfolioState, Position
from meridian_contracts.portfolio_state_key import (
    SCHEMA_JSON as PORTFOLIO_STATE_KEY_SCHEMA_JSON,
)
from meridian_contracts.portfolio_state_key import PortfolioStateKey
from meridian_contracts.risk_snapshot import SCHEMA_JSON as RISK_SNAPSHOT_SCHEMA_JSON
from meridian_contracts.risk_snapshot import RiskSnapshot
from meridian_contracts.risk_snapshot_key import (
    SCHEMA_JSON as RISK_SNAPSHOT_KEY_SCHEMA_JSON,
)
from meridian_contracts.risk_snapshot_key import RiskSnapshotKey
from meridian_contracts.tick import SCHEMA_JSON as TICK_SCHEMA_JSON
from meridian_contracts.tick import Tick
from meridian_contracts.tick_key import SCHEMA_JSON as TICK_KEY_SCHEMA_JSON
from meridian_contracts.tick_key import TickKey

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _round_trip(record_dict: dict, schema_json: str) -> dict:
    schema = avro.schema.parse(schema_json)
    buf = io.BytesIO()
    avro.io.DatumWriter(schema).write(record_dict, avro.io.BinaryEncoder(buf))
    buf.seek(0)
    return avro.io.DatumReader(schema).read(avro.io.BinaryDecoder(buf))


def test_tick_round_trips() -> None:
    tick = Tick(
        instrument_id="AAPL",
        price=Decimal("189.32000000"),
        currency="USD",
        event_time=_NOW,
        ingest_time=_NOW,
        scenario_id="scenario-1",
    )
    back = Tick.from_dict(_round_trip(tick.to_dict(), TICK_SCHEMA_JSON))
    assert back == tick

    key = TickKey(instrument_id="AAPL")
    back_key = TickKey.from_dict(_round_trip(key.to_dict(), TICK_KEY_SCHEMA_JSON))
    assert back_key == key


def test_risk_snapshot_round_trips() -> None:
    snap = RiskSnapshot(
        portfolio_id="portfolio-1",
        as_of=_NOW,
        pricer_version="0.1.0",
        price=Decimal("1234567.87654321"),
        delta=0.63,
        gamma=0.018,
        vega=37.5,
        theta=-6.4,
        rho=53.2,
        var_95=125000.0,
        scenario_id="scenario-1",
        ingest_time=_NOW,
    )
    back = RiskSnapshot.from_dict(_round_trip(snap.to_dict(), RISK_SNAPSHOT_SCHEMA_JSON))
    assert back == snap

    key = RiskSnapshotKey(portfolio_id="portfolio-1")
    back_key = RiskSnapshotKey.from_dict(_round_trip(key.to_dict(), RISK_SNAPSHOT_KEY_SCHEMA_JSON))
    assert back_key == key


def test_portfolio_state_round_trips_including_nested_positions() -> None:
    position = Position(
        portfolio_id="portfolio-1",
        instrument_id="AAPL",
        quantity=Decimal("100.00000000"),
        average_cost=Decimal("150.25000000"),
        as_of_event_time=_NOW,
    )
    state = PortfolioState(
        portfolio_id="portfolio-1",
        positions=[position],
        event_time=_NOW,
        ingest_time=_NOW,
    )
    back = PortfolioState.from_dict(_round_trip(state.to_dict(), PORTFOLIO_STATE_SCHEMA_JSON))
    assert back == state
    assert back.positions[0] == position

    key = PortfolioStateKey(portfolio_id="portfolio-1")
    back_key = PortfolioStateKey.from_dict(_round_trip(key.to_dict(), PORTFOLIO_STATE_KEY_SCHEMA_JSON))
    assert back_key == key


def test_portfolio_state_empty_positions_round_trips() -> None:
    state = PortfolioState(portfolio_id="portfolio-1", positions=[], event_time=_NOW, ingest_time=_NOW)
    back = PortfolioState.from_dict(_round_trip(state.to_dict(), PORTFOLIO_STATE_SCHEMA_JSON))
    assert back == state
