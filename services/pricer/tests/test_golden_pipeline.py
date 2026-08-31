"""A small fixture whose expected snapshots are checked in
(fixtures/golden_snapshots.json), computed independently by
fixtures/generate_golden_snapshots.py -- a script that does not import
pricer.pricing/pricer.portfolio_view, so agreement isn't a tautology."""
import json
from pathlib import Path

from pricer_test_helpers import run_fixture_pipeline

_GOLDEN_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "golden_snapshots.json"


def test_matches_checked_in_golden_snapshots(kafka_stack) -> None:
    produced = run_fixture_pipeline(kafka_stack)
    golden = json.loads(_GOLDEN_PATH.read_text())

    assert len(produced) == len(golden)

    produced_sorted = sorted(produced, key=lambda s: (s.portfolio_id, s.as_of))
    golden_sorted = sorted(golden, key=lambda g: (g["portfolio_id"], g["as_of"]))

    for actual, expected in zip(produced_sorted, golden_sorted, strict=True):
        assert actual.portfolio_id == expected["portfolio_id"]
        assert actual.as_of.isoformat() == expected["as_of"]
        assert actual.pricer_version == expected["pricer_version"]
        assert str(actual.price) == expected["price"]
        assert str(actual.cash_delta) == expected["cash_delta"]
        assert str(actual.cash_gamma) == expected["cash_gamma"]
        assert str(actual.cash_vega) == expected["cash_vega"]
        assert str(actual.cash_theta) == expected["cash_theta"]
        assert str(actual.cash_rho) == expected["cash_rho"]
        assert actual.var_95 == expected["var_95"]
        assert actual.scenario_id == expected["scenario_id"]
        assert actual.oldest_input_event_time.isoformat() == expected["oldest_input_event_time"]
