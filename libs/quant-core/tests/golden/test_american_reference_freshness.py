"""The committed American fixtures match their generator.

Recomputes the first three rows of each fixture with
generate_american_reference.py's own functions. A fixture edited by hand,
or a production lattice change without a regenerated fixture, fails here.
Regenerate with: python libs/quant-core/tests/golden/generate_american_reference.py
"""
import json
from pathlib import Path
from typing import Any

import generate_american_reference as gen
import pytest

_HERE = Path(__file__).parent
_REL_TOL = 1e-12  # round-off guard


def _load(name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads((_HERE / name).read_text())
    return rows


def _assert_rows_match(committed: dict[str, Any], fresh: dict[str, Any]) -> None:
    assert committed.keys() == fresh.keys()
    for key, expected in committed.items():
        actual = fresh[key]
        if isinstance(expected, float):
            assert abs(actual - expected) <= _REL_TOL * abs(expected), f"{key}: committed {expected}, generator {actual}"
        else:
            assert actual == expected, f"{key}: committed {expected}, generator {actual}"


def _case(row: dict[str, Any]) -> tuple[str, float, float, float, float, float, float, bool]:
    return (
        row["label"],
        row["spot"],
        row["strike"],
        row["volatility"],
        row["risk_free_rate"],
        row["dividend_yield"],
        row["time_to_expiry_years"],
        row["is_call"],
    )


@pytest.mark.parametrize("index", range(3))
def test_crr_fixture_is_fresh(index: int) -> None:
    committed = _load("american_crr_reference.json")[index]
    _assert_rows_match(committed, gen.crr_row(_case(committed)))


@pytest.mark.parametrize("index", range(3))
def test_closed_form_fixture_is_fresh(index: int) -> None:
    pytest.importorskip("mpmath")
    committed = _load("american_closed_form_reference.json")[index]
    _assert_rows_match(committed, gen.closed_form_row(_case(committed)))


@pytest.mark.parametrize("index", range(3))
def test_domain_fixture_is_fresh(index: int) -> None:
    committed = _load("american_domain_reference.json")[index]
    point = {k: committed[k] for k in ("spot", "strike", "volatility", "risk_free_rate", "dividend_yield", "time_to_expiry_years", "is_call")}
    assert point == next(p for i, p in enumerate(gen.sampled_c4_points()) if i == index)
    _assert_rows_match(committed, gen.domain_row(point))
