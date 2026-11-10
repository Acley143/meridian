"""ADR-0033, unit level (no Kafka): an American option's statics are
required at reference-data construction, and `price_instrument` reports an
out-of-domain American option with its own error type while every other
failed evaluation stays the generic `UnpricableInstrumentError`."""
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pricer import pricing
from pricer.pricing import (
    OptionMarketInputs,
    UnpricableInstrumentError,
    price_instrument,
)
from pricer.reference_data import InstrumentReference
from quant_core.pricing.american import ModelDomainError
from quant_core.types import OptionRight

_AMER_PUT = InstrumentReference(
    instrument_id="AAPL-AMER-PUT-200",
    instrument_type="VANILLA_AMERICAN_OPTION",
    underlying_id="AAPL",
    currency="USD",
    contract_size=Decimal(100),
    option_type=OptionRight.PUT,
    strike=Decimal("200.00"),
    expiry_iso="2026-06-01T00:00:00Z",
)


def test_a5_american_option_without_strike_fails_at_construction() -> None:
    with pytest.raises(ValueError) as exc_info:
        InstrumentReference(
            instrument_id="AAPL-AMER-PUT-200",
            instrument_type="VANILLA_AMERICAN_OPTION",
            underlying_id="AAPL",
            currency="USD",
            contract_size=Decimal(100),
            option_type=OptionRight.PUT,
            strike=None,
            expiry_iso="2026-06-01T00:00:00Z",
        )
    message = str(exc_info.value)
    assert "VANILLA_AMERICAN_OPTION" in message
    assert "strike" in message


def test_a6_out_of_domain_american_option_raises_the_out_of_domain_type() -> None:
    with pytest.raises(UnpricableInstrumentError) as exc_info:
        price_instrument(
            _AMER_PUT,
            Decimal("150.00"),
            datetime(2026, 1, 1, tzinfo=UTC),
            OptionMarketInputs(volatility=3.0, risk_free_rate=0.05, dividend_yield=0.0),
        )
    error = exc_info.value
    assert isinstance(error, pricing.OutsideModelDomainError)
    assert isinstance(error.__cause__, ModelDomainError)
    assert error.violations == error.__cause__.violations
    assert "AAPL-AMER-PUT-200" in str(error)
    assert "outside the ADR-0031 validated domain" in str(error)
    assert "sigma_root_t" in str(error)


def test_a6_expired_american_option_is_the_generic_unpricable_error() -> None:
    with pytest.raises(UnpricableInstrumentError) as exc_info:
        price_instrument(
            _AMER_PUT,
            Decimal("150.00"),
            datetime(2026, 7, 1, tzinfo=UTC),
            OptionMarketInputs(volatility=0.25, risk_free_rate=0.05, dividend_yield=0.0),
        )
    error = exc_info.value
    assert type(error) is UnpricableInstrumentError
    assert isinstance(error.__cause__, ValueError)
    assert not isinstance(error.__cause__, ModelDomainError)
    assert "is before valuation_time" in str(error)
