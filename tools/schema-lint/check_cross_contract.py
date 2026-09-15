#!/usr/bin/env python3
"""Cross-check contracts/avro/*.avsc against contracts/openapi/*.yaml for the
schemas named in schema_pairing.py (ADR-0026).

Closed-world: every Avro record and every OpenAPI components/schemas entry
must appear in schema_pairing.py, as a pair or as a declared-unpaired entry
with a reason. A schema found on either side that is absent from the
pairing map is a failure, not a silent skip.

For each paired schema this compares, field by field: the field name set,
the type (via the mapping table below), enum symbol sets, nullability/
required-ness (see the docstring on check_nullability), and -- for any
Avro decimal field -- that precision/scale are exactly (38, 8) (ADR-0013).

Does NOT compare: descriptions, field order, defaults, examples.
"""
import json
import sys
from pathlib import Path

import yaml

from schema_pairing import PAIRS, UNPAIRED_AVRO, UNPAIRED_OPENAPI

DECIMAL_PRECISION = 38
DECIMAL_SCALE = 8


class ContractError(Exception):
    """One human-readable line describing a single mismatch."""


# ---------------------------------------------------------------------------
# Avro side
# ---------------------------------------------------------------------------


def collect_avro_records(avro_dir):
    """Return {record_name: (file_name, record_node)} for every named record
    anywhere in avro_dir's *.avsc files, including nested records (e.g.
    Position, nested inside portfolio-state.avsc's positions array) -- a
    one-schema-per-file enumeration would miss those.
    """
    records = {}

    def walk(node, file_name):
        if isinstance(node, dict):
            if node.get("type") == "record" and "name" in node:
                records[node["name"]] = (file_name, node)
            for value in node.values():
                walk(value, file_name)
        elif isinstance(node, list):
            for item in node:
                walk(item, file_name)

    for f in sorted(avro_dir.glob("*.avsc")):
        schema = json.loads(f.read_text())
        walk(schema, f.name)

    return records


def avro_field_map(record_node):
    return {field["name"]: field["type"] for field in record_node["fields"]}


def classify_avro_type(type_node):
    """Return (kind, nullable, extra) for one Avro field's "type" value.

    kind is one of: decimal, timestamp_micros, enum, string, double,
    array_record, unsupported. extra carries kind-specific detail (decimal
    precision/scale, enum symbols, the nested record name for array_record).
    """
    nullable = False
    node = type_node
    if isinstance(node, list):
        if len(node) == 2 and "null" in node:
            nullable = True
            node = node[0] if node[1] == "null" else node[1]
        else:
            return "unsupported", False, {"raw": type_node}

    if node == "string":
        return "string", nullable, {}
    if node == "double":
        return "double", nullable, {}

    if isinstance(node, dict):
        if node.get("logicalType") == "decimal" and node.get("type") == "bytes":
            return (
                "decimal",
                nullable,
                {"precision": node.get("precision"), "scale": node.get("scale")},
            )
        if node.get("logicalType") == "timestamp-micros" and node.get("type") == "long":
            return "timestamp_micros", nullable, {}
        if node.get("type") == "enum":
            return "enum", nullable, {"symbols": set(node.get("symbols", []))}
        if node.get("type") == "array":
            items = node.get("items")
            if isinstance(items, dict) and items.get("type") == "record":
                return "array_record", nullable, {"record_name": items.get("name")}
            return "unsupported", nullable, {"raw": type_node}

    return "unsupported", nullable, {"raw": type_node}


# ---------------------------------------------------------------------------
# OpenAPI side
# ---------------------------------------------------------------------------


def collect_openapi_components(spec):
    return spec.get("components", {}).get("schemas", {})


def classify_openapi_field(field_schema):
    """Return (kind, extra) for one OpenAPI property schema, in the same
    vocabulary as classify_avro_type's kind (minus nullability, which is
    checked separately -- see check_nullability).
    """
    t = field_schema.get("type")
    fmt = field_schema.get("format")
    if t == "string" and "enum" in field_schema:
        return "enum", {"symbols": set(field_schema["enum"])}
    if t == "string" and fmt == "date-time":
        return "timestamp_micros", {}
    if t == "string" and fmt is None:
        return "string", {}
    if t == "number" and fmt == "double":
        return "double", {}
    if t == "array":
        items = field_schema.get("items", {})
        ref = items.get("$ref", "")
        return "array_record", {"ref_component": ref.rsplit("/", 1)[-1] if ref else None}
    return "unsupported", {"raw": field_schema}


# ---------------------------------------------------------------------------
# Mapping table + nullability rule
# ---------------------------------------------------------------------------

# Avro kind -> the OpenAPI kind it must map to. "string" and "decimal" both
# map to plain "string" -- that row declares two different things
# equivalent and is a deliberate hole (ADR-0026).
KIND_MAP = {
    "decimal": "string",
    "timestamp_micros": "timestamp_micros",
    "enum": "enum",
    "string": "string",
    "double": "double",
    "array_record": "array_record",
}


def check_nullability(pair_name, field_name, avro_nullable, openapi_field, required_fields):
    """For paired schemas: an Avro ["null", X] union means nullable: true AND
    required: true -- the field is always present, with a possibly-null
    value. A naive "nullable -> not required" reading is wrong (it would
    fail Instrument's option_type/strike/expiry, which are correctly
    nullable: true and required today) and must not be implemented.
    """
    errors = []
    is_required = field_name in required_fields
    if not is_required:
        errors.append(
            f"{pair_name}.{field_name}: not in OpenAPI 'required' -- every field of a "
            f"paired schema is always present on the wire, nullable or not"
        )

    openapi_nullable = bool(openapi_field.get("nullable", False))
    if avro_nullable and not openapi_nullable:
        errors.append(
            f"{pair_name}.{field_name}: Avro is [\"null\", ...] but OpenAPI is missing nullable: true"
        )
    if openapi_nullable and not avro_nullable:
        errors.append(
            f"{pair_name}.{field_name}: OpenAPI has nullable: true but Avro type is not a null union"
        )
    return errors


def compare_pair(pair, avro_records, openapi_components):
    pair_name = pair["openapi_component"]
    errors = []

    if pair["avro_record"] not in avro_records:
        return [f"{pair_name}: Avro record {pair['avro_record']} not found in contracts/avro"]
    if pair["openapi_component"] not in openapi_components:
        return [f"{pair_name}: OpenAPI component {pair['openapi_component']} not found"]

    _, avro_node = avro_records[pair["avro_record"]]
    openapi_node = openapi_components[pair["openapi_component"]]

    avro_fields = avro_field_map(avro_node)
    openapi_fields = openapi_node.get("properties", {})
    required_fields = set(openapi_node.get("required", []))

    avro_names = set(avro_fields)
    openapi_names = set(openapi_fields)

    for name in sorted(avro_names - openapi_names):
        errors.append(f"{pair_name}.{name}: present in Avro, missing in OpenAPI")
    for name in sorted(openapi_names - avro_names):
        errors.append(f"{pair_name}.{name}: present in OpenAPI, missing in Avro")

    for name in sorted(avro_names & openapi_names):
        avro_kind, avro_nullable, avro_extra = classify_avro_type(avro_fields[name])
        openapi_kind, openapi_extra = classify_openapi_field(openapi_fields[name])

        if avro_kind == "unsupported":
            errors.append(f"{pair_name}.{name}: Avro type not covered by the mapping table: {avro_extra.get('raw')}")
            continue
        if openapi_kind == "unsupported":
            errors.append(f"{pair_name}.{name}: OpenAPI type not covered by the mapping table: {openapi_extra.get('raw')}")
            continue

        expected_openapi_kind = KIND_MAP[avro_kind]
        if openapi_kind != expected_openapi_kind:
            errors.append(
                f"{pair_name}.{name}: Avro is {avro_kind}, expected OpenAPI {expected_openapi_kind}, got {openapi_kind}"
            )
            continue

        if avro_kind == "decimal":
            precision = avro_extra.get("precision")
            scale = avro_extra.get("scale")
            if precision != DECIMAL_PRECISION or scale != DECIMAL_SCALE:
                errors.append(
                    f"{pair_name}.{name}: decimal(precision={precision}, scale={scale}), "
                    f"expected decimal({DECIMAL_PRECISION}, {DECIMAL_SCALE}) (ADR-0013)"
                )

        if avro_kind == "enum":
            avro_symbols = avro_extra["symbols"]
            openapi_symbols = openapi_extra["symbols"]
            if avro_symbols != openapi_symbols:
                only_avro = sorted(avro_symbols - openapi_symbols)
                only_openapi = sorted(openapi_symbols - avro_symbols)
                errors.append(
                    f"{pair_name}.{name}: enum symbols differ -- only in Avro: {only_avro}, only in OpenAPI: {only_openapi}"
                )

        if avro_kind == "array_record":
            expected_ref = avro_extra.get("record_name")
            actual_ref = openapi_extra.get("ref_component")
            if actual_ref != expected_ref:
                errors.append(
                    f"{pair_name}.{name}: array items $ref is {actual_ref!r}, expected {expected_ref!r}"
                )

        errors.extend(
            check_nullability(pair_name, name, avro_nullable, openapi_fields[name], required_fields)
        )

    return errors


# ---------------------------------------------------------------------------
# Closed-world check
# ---------------------------------------------------------------------------


def check_closed_world(avro_records, openapi_components):
    errors = []

    paired_avro = {p["avro_record"] for p in PAIRS}
    paired_openapi = {p["openapi_component"] for p in PAIRS}

    known_avro = paired_avro | set(UNPAIRED_AVRO)
    known_openapi = paired_openapi | set(UNPAIRED_OPENAPI)

    for name in sorted(set(avro_records) - known_avro):
        errors.append(f"Avro record {name!r} is not in schema_pairing.py (pair or declared-unpaired)")
    for name in sorted(set(openapi_components) - known_openapi):
        errors.append(f"OpenAPI component {name!r} is not in schema_pairing.py (pair or declared-unpaired)")

    for name in sorted(known_avro - set(avro_records)):
        errors.append(f"schema_pairing.py names Avro record {name!r}, which does not exist in contracts/avro")
    for name in sorted(known_openapi - set(openapi_components)):
        errors.append(f"schema_pairing.py names OpenAPI component {name!r}, which does not exist in the spec")

    return errors


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(avro_dir: Path, openapi_path: Path):
    avro_records = collect_avro_records(avro_dir)
    spec = yaml.safe_load(openapi_path.read_text())
    openapi_components = collect_openapi_components(spec)

    errors = check_closed_world(avro_records, openapi_components)
    for pair in PAIRS:
        errors.extend(compare_pair(pair, avro_records, openapi_components))

    return errors


def main(argv):
    if len(argv) != 3:
        print("usage: check_cross_contract.py <avro-dir> <openapi-spec.yaml>", file=sys.stderr)
        return 2

    avro_dir = Path(argv[1])
    openapi_path = Path(argv[2])

    errors = run(avro_dir, openapi_path)

    if errors:
        print("Errors:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(
        f"OK  {len(PAIRS)} paired schema(s) agree, "
        f"{len(UNPAIRED_AVRO)} Avro + {len(UNPAIRED_OPENAPI)} OpenAPI schema(s) declared unpaired, "
        f"no schema outside the pairing map."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
