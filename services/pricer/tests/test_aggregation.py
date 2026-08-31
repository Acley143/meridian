"""Task 5: ADR-0014 (contract_size multiplier) and ADR-0017 (cash-Greek
aggregation) regression tests. Pure -- no Kafka needed, `pricer.pricing`
takes plain values."""
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pricer.pricing import (
    aggregate_portfolio,
    aggregate_position,
    price_instrument,
)
from pricer.reference_data import InstrumentReference, load_reference_data

_VALUATION_TIME = datetime(2026, 1, 2, 9, 30, 1, tzinfo=UTC)
_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_contract_size_multiplier_is_applied() -> None:
    """ADR-0014's required regression test: a non-unit contract_size
    (100) must produce a value distinguishable from the un-multiplied
    per-unit one -- not a general smoke test."""
    reference = InstrumentReference(
        instrument_id="X",
        instrument_type="EQUITY",
        underlying_id="X",
        currency="USD",
        contract_size=Decimal(100),
    )
    spot = Decimal("50.00")
    quantity = Decimal(10)

    pricing_result = price_instrument(reference, spot, _VALUATION_TIME)
    contribution = aggregate_position(pricing_result, quantity, reference.contract_size, spot)

    unmultiplied = spot * quantity  # what you'd get if contract_size were silently dropped
    correctly_multiplied = spot * quantity * reference.contract_size

    assert contribution.price == correctly_multiplied.quantize(Decimal("1E-8"))
    assert contribution.price != unmultiplied.quantize(Decimal("1E-8"))


def test_cash_delta_uses_1_percent_basis_not_1_00() -> None:
    """ADR-0017: cash_delta/cash_gamma use a 1% relative-move basis, unlike
    the per-unit Greeks (1.00 absolute) -- a regression test for silently
    dropping the 0.01 factor."""
    reference = InstrumentReference(
        instrument_id="X",
        instrument_type="EQUITY",
        underlying_id="X",
        currency="USD",
        contract_size=Decimal(1),
    )
    spot = Decimal("200.00")
    quantity = Decimal(1)
    pricing_result = price_instrument(reference, spot, _VALUATION_TIME)  # delta == 1.0 for equity

    contribution = aggregate_position(pricing_result, quantity, reference.contract_size, spot)

    # delta(1.0) * spot(200) * 0.01 * qty(1) * contract_size(1) = 2.00
    assert contribution.cash_delta == Decimal("2.00000000")


def test_cash_gamma_is_not_a_naive_sum_of_raw_per_unit_gammas_across_underlyings() -> None:
    """ADR-0017's required regression test: portfolio-level cash_gamma must
    not be (or be derived from) a naive sum of raw per-unit gammas across
    different underlyings -- that sum is not even in the same units.
    Fixture values are chosen so the two numbers differ by orders of
    magnitude, so a wrong implementation can't pass by coincidence."""
    reference_data = load_reference_data(_FIXTURES_DIR / "instruments.yaml")
    call_ref = reference_data.get("AAPL-CALL-150")
    put_ref = reference_data.get("MSFT-PUT-280")

    call_spot = Decimal("150.00")
    put_spot = Decimal("200.00")
    call_quantity = Decimal(10)
    put_quantity = Decimal(-5)

    call_pricing = price_instrument(call_ref, call_spot, _VALUATION_TIME)
    put_pricing = price_instrument(put_ref, put_spot, _VALUATION_TIME)

    # The mistake this test exists to catch: summing raw per-unit gammas
    # directly, ignoring spot/basis/contract_size/quantity entirely.
    naive_raw_sum_gamma = call_pricing.gamma + put_pricing.gamma

    call_contribution = aggregate_position(call_pricing, call_quantity, call_ref.contract_size, call_spot)
    put_contribution = aggregate_position(put_pricing, put_quantity, put_ref.contract_size, put_spot)
    portfolio = aggregate_portfolio([call_contribution, put_contribution])

    # Different type (Decimal cash amount vs. float per-unit sensitivity)
    # and, even compared as magnitudes, different by orders of magnitude --
    # not a coincidental near-miss either way.
    assert isinstance(portfolio.cash_gamma, Decimal)
    assert abs(float(portfolio.cash_gamma) - naive_raw_sum_gamma) > 1.0
    assert round(float(portfolio.cash_gamma), 4) != round(naive_raw_sum_gamma, 4)


def test_aggregate_portfolio_sums_across_positions() -> None:
    reference = InstrumentReference(
        instrument_id="X",
        instrument_type="EQUITY",
        underlying_id="X",
        currency="USD",
        contract_size=Decimal(1),
    )
    spot = Decimal("10.00")
    pricing_result = price_instrument(reference, spot, _VALUATION_TIME)

    a = aggregate_position(pricing_result, Decimal(5), reference.contract_size, spot)
    b = aggregate_position(pricing_result, Decimal(3), reference.contract_size, spot)
    total = aggregate_portfolio([a, b])

    assert total.price == a.price + b.price
    assert total.cash_delta == a.cash_delta + b.cash_delta
