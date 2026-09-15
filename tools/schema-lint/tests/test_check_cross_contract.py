"""Tests for check_cross_contract.py (ADR-0026).

These exercise the checker against synthetic fixture schemas in a tmp_path,
never by mutating the real contracts -- except the final test, which runs
the checker against the real contracts/avro and contracts/openapi and must
pass. If it doesn't, the checker is wrong, not the contracts.
"""
import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_cross_contract as cc  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]

BASE_AVRO = {
    "type": "record",
    "name": "Widget",
    "namespace": "com.test",
    "fields": [
        {"name": "id", "type": "string"},
        {
            "name": "amount",
            "type": {"type": "bytes", "logicalType": "decimal", "precision": 38, "scale": 8},
        },
        {
            "name": "status",
            "type": {"type": "enum", "name": "Status", "symbols": ["OPEN", "CLOSED"]},
        },
        {"name": "created", "type": {"type": "long", "logicalType": "timestamp-micros"}},
        {"name": "score", "type": "double"},
    ],
}

BASE_OPENAPI_COMPONENT = {
    "type": "object",
    "required": ["id", "amount", "status", "created", "score"],
    "properties": {
        "id": {"type": "string"},
        "amount": {"type": "string"},
        "status": {"type": "string", "enum": ["OPEN", "CLOSED"]},
        "created": {"type": "string", "format": "date-time"},
        "score": {"type": "number", "format": "double"},
    },
}

BASE_PAIRS = [
    {"avro_file": "widget.avsc", "avro_record": "Widget", "openapi_component": "Widget"}
]


def write_fixture(tmp_path, avro_record, openapi_component, extra_avro_records=None, extra_openapi_components=None):
    avro_dir = tmp_path / "avro"
    avro_dir.mkdir()
    (avro_dir / "widget.avsc").write_text(json.dumps(avro_record))
    for name, node in (extra_avro_records or {}).items():
        (avro_dir / f"{name.lower()}.avsc").write_text(json.dumps(node))

    components = {"Widget": openapi_component}
    components.update(extra_openapi_components or {})
    spec = {
        "openapi": "3.0.3",
        "paths": {},
        "components": {"schemas": components},
    }
    openapi_path = tmp_path / "service-api.yaml"
    openapi_path.write_text(yaml.safe_dump(spec))

    return avro_dir, openapi_path


def run_with_map(tmp_path, monkeypatch, avro_record, openapi_component, pairs=None,
                  unpaired_avro=None, unpaired_openapi=None,
                  extra_avro_records=None, extra_openapi_components=None):
    monkeypatch.setattr(cc, "PAIRS", pairs if pairs is not None else BASE_PAIRS)
    monkeypatch.setattr(cc, "UNPAIRED_AVRO", unpaired_avro or {})
    monkeypatch.setattr(cc, "UNPAIRED_OPENAPI", unpaired_openapi or {})
    avro_dir, openapi_path = write_fixture(
        tmp_path, avro_record, openapi_component, extra_avro_records, extra_openapi_components
    )
    return cc.run(avro_dir, openapi_path)


def test_base_fixture_passes(tmp_path, monkeypatch):
    errors = run_with_map(tmp_path, monkeypatch, BASE_AVRO, BASE_OPENAPI_COMPONENT)
    assert errors == []


def test_field_missing_from_openapi_fails(tmp_path, monkeypatch):
    openapi = copy.deepcopy(BASE_OPENAPI_COMPONENT)
    del openapi["properties"]["score"]
    openapi["required"].remove("score")
    errors = run_with_map(tmp_path, monkeypatch, BASE_AVRO, openapi)
    assert any("score" in e and "missing in OpenAPI" in e for e in errors)


def test_field_missing_from_avro_fails(tmp_path, monkeypatch):
    openapi = copy.deepcopy(BASE_OPENAPI_COMPONENT)
    openapi["properties"]["extra_field"] = {"type": "string"}
    openapi["required"].append("extra_field")
    errors = run_with_map(tmp_path, monkeypatch, BASE_AVRO, openapi)
    assert any("extra_field" in e and "missing in Avro" in e for e in errors)


def test_avro_enum_extra_symbol_fails(tmp_path, monkeypatch):
    avro = copy.deepcopy(BASE_AVRO)
    avro["fields"][2]["type"]["symbols"].append("PENDING")
    errors = run_with_map(tmp_path, monkeypatch, avro, BASE_OPENAPI_COMPONENT)
    assert any("status" in e and "enum symbols differ" in e for e in errors)


def test_type_violating_mapping_table_fails(tmp_path, monkeypatch):
    openapi = copy.deepcopy(BASE_OPENAPI_COMPONENT)
    openapi["properties"]["score"] = {"type": "string"}
    errors = run_with_map(tmp_path, monkeypatch, BASE_AVRO, openapi)
    assert any("score" in e and "Avro is double" in e for e in errors)


def test_wrong_decimal_precision_scale_fails(tmp_path, monkeypatch):
    avro = copy.deepcopy(BASE_AVRO)
    avro["fields"][1]["type"]["precision"] = 20
    avro["fields"][1]["type"]["scale"] = 4
    errors = run_with_map(tmp_path, monkeypatch, avro, BASE_OPENAPI_COMPONENT)
    assert any("amount" in e and "decimal(precision=20, scale=4)" in e for e in errors)


def test_new_avro_schema_absent_from_map_fails(tmp_path, monkeypatch):
    orphan = {
        "type": "record",
        "name": "Orphan",
        "namespace": "com.test",
        "fields": [{"name": "x", "type": "string"}],
    }
    errors = run_with_map(
        tmp_path, monkeypatch, BASE_AVRO, BASE_OPENAPI_COMPONENT,
        extra_avro_records={"Orphan": orphan},
    )
    assert any("Orphan" in e and "not in schema_pairing.py" in e for e in errors)


def test_new_openapi_component_absent_from_map_fails(tmp_path, monkeypatch):
    orphan = {"type": "object", "required": [], "properties": {}}
    errors = run_with_map(
        tmp_path, monkeypatch, BASE_AVRO, BASE_OPENAPI_COMPONENT,
        extra_openapi_components={"OrphanApi": orphan},
    )
    assert any("OrphanApi" in e and "not in schema_pairing.py" in e for e in errors)


def test_real_contracts_pass():
    errors = cc.run(
        REPO_ROOT / "contracts" / "avro",
        REPO_ROOT / "contracts" / "openapi" / "service-api.yaml",
    )
    assert errors == []
