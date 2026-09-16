"""Schema evolution test: verify the BACKWARD-compatibility enforcement
mechanism itself, not just cite the rule.

Same principle as libs/quant-core's purity fixture (see its PLAN.md session
log): a check that has never been observed to fail proves nothing. For
every schema currently in contracts/avro/, this confirms both directions:
adding a field WITH a default is accepted, and adding a field WITHOUT one
is rejected. If either assertion ever flips, the enforcement mechanism
(backward_compat.py, and by extension the real registry it approximates)
is broken, not just the schema under test.
"""
import copy
import json
from pathlib import Path

import pytest
from backward_compat import is_backward_compatible

_AVRO_DIR = Path(__file__).resolve().parents[2] / "avro"
_SCHEMAS = sorted(_AVRO_DIR.glob("*.avsc"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


@pytest.mark.parametrize("schema_path", _SCHEMAS, ids=lambda p: p.name)
def test_adding_field_with_default_is_backward_compatible(schema_path: Path) -> None:
    old_schema = _load(schema_path)
    new_schema = copy.deepcopy(old_schema)
    new_schema["fields"].append(
        {
            "name": "_evolution_probe_with_default",
            "type": "string",
            "default": "",
            "doc": "Test-only field added by test_schema_evolution.py; never a real schema field.",
        }
    )

    compatible, detail = is_backward_compatible(old_schema, new_schema)
    assert compatible, f"{schema_path.name}: adding a field WITH a default should be BACKWARD-compatible, but was rejected: {detail}"


@pytest.mark.parametrize("schema_path", _SCHEMAS, ids=lambda p: p.name)
def test_adding_field_without_default_is_rejected(schema_path: Path) -> None:
    old_schema = _load(schema_path)
    new_schema = copy.deepcopy(old_schema)
    new_schema["fields"].append(
        {
            "name": "_evolution_probe_without_default",
            "type": "string",
            "doc": "Test-only field added by test_schema_evolution.py; never a real schema field.",
        }
    )

    compatible, _detail = is_backward_compatible(old_schema, new_schema)
    assert not compatible, (
        f"{schema_path.name}: adding a field WITHOUT a default was accepted as BACKWARD-compatible -- "
        "the enforcement mechanism is broken, not just this schema."
    )


def _find_enum(node, name: str):
    """Depth-first search for a named enum definition anywhere in a schema."""
    if isinstance(node, dict):
        if node.get("type") == "enum" and node.get("name") == name:
            return node
        for value in node.values():
            found = _find_enum(value, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_enum(item, name)
            if found is not None:
                return found
    return None


def test_curve_kind_identical_in_market_curves_and_market_curves_key() -> None:
    value_schema = _load(_AVRO_DIR / "market-curves.avsc")
    key_schema = _load(_AVRO_DIR / "market-curves-key.avsc")

    value_curve_kind = _find_enum(value_schema, "CurveKind")
    key_curve_kind = _find_enum(key_schema, "CurveKind")

    assert value_curve_kind is not None, "CurveKind not found in market-curves.avsc"
    assert key_curve_kind is not None, "CurveKind not found in market-curves-key.avsc"
    assert value_curve_kind.get("namespace") == key_curve_kind.get("namespace"), (
        "CurveKind namespace differs between market-curves.avsc and market-curves-key.avsc"
    )
    assert value_curve_kind["symbols"] == key_curve_kind["symbols"], (
        "CurveKind symbols differ (or differ in order) between market-curves.avsc and "
        "market-curves-key.avsc: "
        f"{value_curve_kind['symbols']!r} != {key_curve_kind['symbols']!r}"
    )
