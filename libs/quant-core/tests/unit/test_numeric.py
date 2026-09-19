from decimal import Decimal

import pytest
from quant_core.numeric import convert_money, to_model, to_money


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


def test_convert_money_representative_value_is_exact() -> None:
    # 12345.67890123 * 1.08123456, summed by hand from the partial products:
    #   * 1          = 12345.67890123
    #   * 0.08       =   987.6543120984
    #   * 0.001      =    12.34567890123
    #   * 0.0002     =     2.469135780246
    #   * 0.00003    =     0.3703703670369
    #   * 0.000004   =     0.04938271560492
    #   * 0.0000005  =     0.006172839450615
    #   * 0.00000006 =     0.0007407407340738
    # Total 13348.5746946727025088, which rounds to scale 8 as below.
    assert convert_money(Decimal("12345.67890123"), Decimal("1.08123456")) == Decimal(
        "13348.57469467"
    )


def test_convert_money_quantises_to_scale_8() -> None:
    result = convert_money(Decimal(1), Decimal("1.5"))
    assert result == Decimal("1.50000000")
    assert result.as_tuple().exponent == -8


def test_convert_money_rounds_half_to_even_at_a_tie() -> None:
    # 0.00000005 * 0.5 = 0.000000025 -- an exact tie at the 8th place: half-even
    # keeps the even digit (2), half-up would give 3.
    assert convert_money(Decimal("0.00000005"), Decimal("0.5")) == Decimal("0.00000002")
    # 0.00000015 * 0.5 = 0.000000075 -- tie between 7 and 8: half-even rounds to 8.
    assert convert_money(Decimal("0.00000015"), Decimal("0.5")) == Decimal("0.00000008")


def test_convert_money_rate_of_one_returns_the_amount_unchanged() -> None:
    result = convert_money(Decimal("-27865.749635"), Decimal(1))
    assert result == Decimal("-27865.74963500")
    assert result.as_tuple().exponent == -8


@pytest.mark.parametrize(
    "bad_rate",
    [Decimal(0), Decimal("-1.08"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_convert_money_rejects_a_rate_that_is_not_finite_and_strictly_positive(
    bad_rate: Decimal,
) -> None:
    with pytest.raises(ValueError, match="strictly positive"):
        convert_money(Decimal(100), bad_rate)


def test_convert_money_error_names_the_rate() -> None:
    with pytest.raises(ValueError, match="-1.08"):
        convert_money(Decimal(100), Decimal("-1.08"))
