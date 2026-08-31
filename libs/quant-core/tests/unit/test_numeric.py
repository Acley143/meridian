from decimal import Decimal

from quant_core.numeric import to_model, to_money


def test_to_model_basic() -> None:
    assert to_model(Decimal("100.5")) == 100.5


def test_to_money_quantises_to_scale_8() -> None:
    result = to_money(1.0 / 3.0)
    assert result == Decimal("0.33333333")
    assert result.as_tuple().exponent == -8


def test_to_money_rounds_half_to_even_not_half_up() -> None:
    # 0.125 and 0.375 are exact binary fractions (1/8, 3/8), so quantizing
    # to 2 decimal places is a genuine halfway case: half-up would send both
    # to .13/.38 (a consistent upward bias); half-even alternates.
    assert Decimal("0.125").quantize(Decimal("0.01"), rounding="ROUND_HALF_EVEN") == Decimal("0.12")
    assert Decimal("0.375").quantize(Decimal("0.01"), rounding="ROUND_HALF_EVEN") == Decimal("0.38")
    # to_money applies the same rounding mode, at scale 8.
    assert to_money(0.125).as_tuple().exponent == -8


def test_to_money_always_returns_scale_8() -> None:
    for value in (0.0, 1.0, -1.0, 123.456789125, 1e-10):
        assert to_money(value).as_tuple().exponent == -8
