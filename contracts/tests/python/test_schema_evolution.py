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
