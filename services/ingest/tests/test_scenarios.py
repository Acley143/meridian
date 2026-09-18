"""Scenario id uniqueness (services/ingest/scenarios/README.md): editing a
checked-in scenario's parameters under an existing scenario_id would make
every historical snapshot tagged with it a lie, so every scenario file must
declare a distinct id."""
from pathlib import Path

import pytest
import yaml
from ingest.scenario import load_all_scenarios, load_scenario

_SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "scenarios"
_SMALL_DETERMINISTIC_V2 = _SCENARIOS_DIR / "small-deterministic-v2.yaml"
_INSTRUMENTS_FIXTURE = (
    Path(__file__).resolve().parents[2] / "pricer" / "fixtures" / "instruments.yaml"
)
_CURVES_FIXTURE = Path(__file__).resolve().parents[2] / "pricer" / "fixtures" / "curves.yaml"

_SCENARIO_HEADER = """\
scenario_id: {scenario_id}
seed: 1
start_time: "2026-01-01T00:00:00Z"
tick_interval_seconds: 1.0
tick_count: 1
instruments:
  AAPL:
    s0: "150.00"
    drift: 0.05
    volatility: 0.20
    currency: USD
"""


def test_scenario_ids_are_unique_across_the_directory() -> None:
    scenarios = load_all_scenarios(_SCENARIOS_DIR)
    ids = [s.scenario_id for s in scenarios]
    assert len(ids) == len(set(ids)), f"duplicate scenario_id in {_SCENARIOS_DIR}: {ids}"


def test_at_least_one_scenario_file_present() -> None:
    assert load_all_scenarios(_SCENARIOS_DIR), f"no scenario files found in {_SCENARIOS_DIR}"


def test_small_deterministic_v2_loads_exactly_the_five_declared_curves() -> None:
    scenario = load_scenario(_SMALL_DETERMINISTIC_V2)

    expected = {
        ("RISK_FREE_RATE", "USD"): (0.04, None),
        ("VOLATILITY", "AAPL"): (0.25, None),
        ("DIVIDEND_YIELD", "AAPL"): (0.0, None),
        ("VOLATILITY", "MSFT"): (0.35, None),
        ("DIVIDEND_YIELD", "MSFT"): (0.0, None),
    }
    assert len(scenario.curves) == len(expected)
    actual = {(c.kind, c.curve_id): (c.value_float, c.value_decimal) for c in scenario.curves}
    assert actual == expected


@pytest.mark.parametrize("scenario_path", ["small-deterministic.yaml", "throughput-1000.yaml"])
def test_scenarios_without_a_curves_section_load_with_no_curves(scenario_path: str) -> None:
    scenario = load_scenario(_SCENARIOS_DIR / scenario_path)
    assert scenario.curves == ()


def test_curve_loading_rejects_unknown_kind(tmp_path: Path) -> None:
    scenario_id = "bad-curve-kind"
    path = tmp_path / "scenario.yaml"
    path.write_text(
        _SCENARIO_HEADER.format(scenario_id=scenario_id)
        + "curves:\n  - kind: NOT_A_KIND\n    curve_id: USD\n    value: 0.04\n"
    )
    with pytest.raises(ValueError, match=scenario_id):
        load_scenario(path)


def test_curve_loading_rejects_unquoted_fx_rate_value(tmp_path: Path) -> None:
    scenario_id = "bad-fx-rate-value"
    path = tmp_path / "scenario.yaml"
    path.write_text(
        _SCENARIO_HEADER.format(scenario_id=scenario_id)
        + "curves:\n  - kind: FX_RATE\n    curve_id: EURUSD\n    value: 1.08\n"
    )
    with pytest.raises(ValueError, match=scenario_id):
        load_scenario(path)


def test_curve_loading_rejects_quoted_volatility_value(tmp_path: Path) -> None:
    scenario_id = "bad-volatility-value"
    path = tmp_path / "scenario.yaml"
    path.write_text(
        _SCENARIO_HEADER.format(scenario_id=scenario_id)
        + 'curves:\n  - kind: VOLATILITY\n    curve_id: AAPL\n    value: "0.25"\n'
    )
    with pytest.raises(ValueError, match=scenario_id):
        load_scenario(path)


def test_curve_loading_rejects_boolean_volatility_value(tmp_path: Path) -> None:
    """`bool` is a Python `int` subclass, so this must be checked explicitly
    rather than relying on `isinstance(value, (int, float))`."""
    scenario_id = "bad-boolean-value"
    path = tmp_path / "scenario.yaml"
    path.write_text(
        _SCENARIO_HEADER.format(scenario_id=scenario_id)
        + "curves:\n  - kind: VOLATILITY\n    curve_id: AAPL\n    value: true\n"
    )
    with pytest.raises(ValueError, match=scenario_id):
        load_scenario(path)


def test_curve_loading_rejects_repeated_kind_and_curve_id(tmp_path: Path) -> None:
    scenario_id = "bad-repeated-curve"
    path = tmp_path / "scenario.yaml"
    path.write_text(
        _SCENARIO_HEADER.format(scenario_id=scenario_id)
        + "curves:\n"
        + "  - kind: RISK_FREE_RATE\n    curve_id: USD\n    value: 0.04\n"
        + "  - kind: RISK_FREE_RATE\n    curve_id: USD\n    value: 0.05\n"
    )
    with pytest.raises(ValueError, match=scenario_id):
        load_scenario(path)


def test_curve_loading_rejects_unquoted_boolean_curve_id(tmp_path: Path) -> None:
    """PyYAML reads unquoted ON/OFF/YES/NO as booleans -- a real ticker
    named ON must be quoted, and an unquoted one must fail loudly at load,
    not partway through Avro serialization."""
    scenario_id = "bad-boolean-curve-id"
    path = tmp_path / "scenario.yaml"
    path.write_text(
        _SCENARIO_HEADER.format(scenario_id=scenario_id)
        + "curves:\n  - kind: VOLATILITY\n    curve_id: ON\n    value: 0.25\n"
    )
    with pytest.raises(ValueError, match=scenario_id):
        load_scenario(path)


def test_curve_loading_rejects_extra_key(tmp_path: Path) -> None:
    scenario_id = "bad-extra-key"
    path = tmp_path / "scenario.yaml"
    path.write_text(
        _SCENARIO_HEADER.format(scenario_id=scenario_id)
        + "curves:\n  - kind: VOLATILITY\n    curve_id: AAPL\n    value: 0.25\n    units: pct\n"
    )
    with pytest.raises(ValueError, match=scenario_id):
        load_scenario(path)


def test_curve_loading_rejects_missing_key(tmp_path: Path) -> None:
    scenario_id = "bad-missing-key"
    path = tmp_path / "scenario.yaml"
    path.write_text(
        _SCENARIO_HEADER.format(scenario_id=scenario_id)
        + "curves:\n  - kind: VOLATILITY\n    curve_id: AAPL\n"
    )
    with pytest.raises(ValueError, match=scenario_id):
        load_scenario(path)


def test_curve_loading_rejects_unparseable_fx_rate_value(tmp_path: Path) -> None:
    scenario_id = "bad-fx-rate-not-a-number"
    path = tmp_path / "scenario.yaml"
    path.write_text(
        _SCENARIO_HEADER.format(scenario_id=scenario_id)
        + 'curves:\n  - kind: FX_RATE\n    curve_id: EURUSD\n    value: "abc"\n'
    )
    with pytest.raises(ValueError, match=scenario_id):
        load_scenario(path)


def test_small_deterministic_v2_curves_match_pricer_curve_fixture() -> None:
    """Permanent guard: small-deterministic-v2's curves must match the curve
    values services/pricer prices with (services/pricer/fixtures/curves.yaml,
    ADR-0027), not services/pricer/fixtures/instruments.yaml's market fields,
    which are retired in a later session."""
    scenario = load_scenario(_SMALL_DETERMINISTIC_V2)
    curves_by_key = {(c.kind, c.curve_id): c for c in scenario.curves}

    curves_fixture = yaml.safe_load(_CURVES_FIXTURE.read_text())
    expected_by_key = {
        (curve["kind"], curve["curve_id"]): curve["value"]
        for curve in curves_fixture["curves"]
    }

    instruments_fixture = yaml.safe_load(_INSTRUMENTS_FIXTURE.read_text())
    required_keys: set[tuple[str, str]] = set()
    for instrument in instruments_fixture["instruments"].values():
        if instrument["instrument_type"] != "VANILLA_EUROPEAN_OPTION":
            continue
        currency = instrument["currency"]
        underlying_id = instrument["underlying_id"]

        rate_key = ("RISK_FREE_RATE", currency)
        vol_key = ("VOLATILITY", underlying_id)
        div_key = ("DIVIDEND_YIELD", underlying_id)
        required_keys |= {rate_key, vol_key, div_key}

    for key in required_keys:
        assert key in curves_by_key, f"missing {key} in {_SMALL_DETERMINISTIC_V2}"
        assert key in expected_by_key, f"missing {key} in {_CURVES_FIXTURE}"
        assert curves_by_key[key].value_float == expected_by_key[key]

    assert set(curves_by_key) == required_keys, (
        f"small-deterministic-v2 declares curves beyond the required set: "
        f"{set(curves_by_key) - required_keys}"
    )
    assert set(expected_by_key) == required_keys, (
        f"{_CURVES_FIXTURE} declares curves beyond the required set: "
        f"{set(expected_by_key) - required_keys}"
    )
