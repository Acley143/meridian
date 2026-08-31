"""Scenario id uniqueness (services/ingest/scenarios/README.md): editing a
checked-in scenario's parameters under an existing scenario_id would make
every historical snapshot tagged with it a lie, so every scenario file must
declare a distinct id."""
from pathlib import Path

from ingest.scenario import load_all_scenarios

_SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "scenarios"


def test_scenario_ids_are_unique_across_the_directory() -> None:
    scenarios = load_all_scenarios(_SCENARIOS_DIR)
    ids = [s.scenario_id for s in scenarios]
    assert len(ids) == len(set(ids)), f"duplicate scenario_id in {_SCENARIOS_DIR}: {ids}"


def test_at_least_one_scenario_file_present() -> None:
    assert load_all_scenarios(_SCENARIOS_DIR), f"no scenario files found in {_SCENARIOS_DIR}"
