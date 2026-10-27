"""ADR-0032 Decisions 2 and 4: `price_instrument` converts a failed model
evaluation into `UnpricableInstrumentError`, for exactly ValueError,
OverflowError and decimal.InvalidOperation, and lets every other exception
through. Pure -- no Kafka needed.

The overflow and InvalidOperation inputs are the ones found by probing
`black_scholes.price` with extreme curve values: RISK_FREE_RATE and
DIVIDEND_YIELD are validated only as finite (`validate_market_curve`)."""
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import pytest
from pricer import pricing
from pricer.pricing import (
    OptionMarketInputs,
    UnpricableInstrumentError,
    price_instrument,
)
from pricer.reference_data import InstrumentReference
from quant_core.types import OptionRight

_VALUATION_TIME = datetime(2026, 1, 2, 9, 30, 1, tzinfo=UTC)
_NORMAL_MARKET = OptionMarketInputs(volatility=0.25, risk_free_rate=0.04, dividend_yield=0.0)

_CALL = InstrumentReference(
    instrument_id="AAPL-CALL-150",
    instrument_type="VANILLA_EUROPEAN_OPTION",
    underlying_id="AAPL",
    currency="USD",
    contract_size=Decimal(100),
    option_type=OptionRight.CALL,
    strike=Decimal("150.00"),
    expiry_iso="2027-01-04T09:30:01Z",
)


@pytest.mark.parametrize(
    ("spot", "market", "cause"),
    [
        # MarketState rejects a non-positive spot.
        pytest.param(Decimal(0), _NORMAL_MARKET, ValueError, id="spot-0-ValueError"),
        # exp(-r * T) with r = -1000 and T ~ 1 overflows.
        pytest.param(
            Decimal("150.00"),
            OptionMarketInputs(volatility=0.25, risk_free_rate=-1000.0, dividend_yield=0.0),
            OverflowError,
            id="rate-minus-1000-OverflowError",
        ),
        # r = 700 and q = -700: each discount factor is finite but the price is
        # infinite, which to_money cannot quantise.
        pytest.param(
            Decimal("150.00"),
            OptionMarketInputs(volatility=0.25, risk_free_rate=700.0, dividend_yield=-700.0),
            InvalidOperation,
            id="rate-700-dividend-minus-700-InvalidOperation",
        ),
    ],
)
def test_a_failed_model_evaluation_is_an_unpricable_instrument(
    spot: Decimal, market: OptionMarketInputs, cause: type[BaseException]
) -> None:
    """T4. The original exception is kept as `__cause__`, and the message
    names the instrument and the original exception's type."""
    with pytest.raises(UnpricableInstrumentError) as excinfo:
        price_instrument(_CALL, spot, _VALUATION_TIME, market)
    assert type(excinfo.value.__cause__) is cause
    assert str(excinfo.value).startswith("AAPL-CALL-150: VANILLA_EUROPEAN_OPTION could not be priced: ")
    assert cause.__name__ in str(excinfo.value)


def test_any_other_exception_from_the_model_fails_fast(monkeypatch) -> None:
    """T6. ADR-0032 Decision 4: the catch is narrow. A ZeroDivisionError from
    the pricer is a defect and must escape as itself, not be reported as an
    unpriceable instrument."""

    def broken_pricer(option, market_state):
        raise ZeroDivisionError("defect")

    monkeypatch.setattr(pricing, "black_scholes_price", broken_pricer)
    with pytest.raises(ZeroDivisionError, match="defect"):
        price_instrument(_CALL, Decimal("150.00"), _VALUATION_TIME, _NORMAL_MARKET)
