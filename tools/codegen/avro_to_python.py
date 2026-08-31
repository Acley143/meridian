"""Avro .avsc -> Python dataclass generator.

Deterministic, single-purpose: given a parsed .avsc record schema (already
loaded as a Python dict, preserving field order), emit Python source
defining one frozen dataclass per record type in the schema (nested records
first, so a later class's field types are already defined), each with
`to_dict`/`from_dict` for round-tripping through `avro.io.DatumWriter` /
`DatumReader`, plus a `SCHEMA_JSON` constant holding the exact source
`.avsc` text so a caller never needs a filesystem path to the schema at
runtime.

Not a general Avro-to-Python compiler -- covers exactly the type shapes
used in contracts/avro/*.avsc (record, string, double, boolean, decimal
bytes, timestamp-micros long, array<record>, map<double>, enum, nullable
union [null, X] added for ADR-0019's reference-instruments.avsc). Extend
`_python_type`/`_to_dict_expr`/`_from_dict_expr` together if a new shape
shows up; each keys off the same Avro type-shape switch, so they must
agree with each other or round-tripping silently breaks for the new shape.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class _Field:
    name: str
    avro_type: Any


@dataclass
class _RecordDef:
    name: str
    doc: str
    fields: list[_Field]


@dataclass
class _EnumDef:
    name: str
    symbols: list[str]


def _is_decimal(t: Any) -> bool:
    return isinstance(t, dict) and t.get("logicalType") == "decimal"


def _is_timestamp_micros(t: Any) -> bool:
    return isinstance(t, dict) and t.get("logicalType") == "timestamp-micros"


def _is_record(t: Any) -> bool:
    return isinstance(t, dict) and t.get("type") == "record"


def _is_array(t: Any) -> bool:
    return isinstance(t, dict) and t.get("type") == "array"


def _is_map(t: Any) -> bool:
    return isinstance(t, dict) and t.get("type") == "map"


def _is_enum(t: Any) -> bool:
    return isinstance(t, dict) and t.get("type") == "enum"


def _is_nullable_union(t: Any) -> bool:
    return isinstance(t, list) and len(t) == 2 and "null" in t


def _union_inner(t: Any) -> Any:
    """The non-null member of a [null, X] union."""
    return next(member for member in t if member != "null")


def collect_records(schema: dict[str, Any]) -> list[_RecordDef]:
    """Walk a record schema, returning nested records before their parent."""
    records: list[_RecordDef] = []
    seen: set[str] = set()

    def visit(node: dict[str, Any]) -> None:
        for field in node["fields"]:
            t = field["type"]
            if _is_nullable_union(t):
                t = _union_inner(t)
            if _is_record(t):
                visit(t)
            elif _is_array(t) and _is_record(t["items"]):
                visit(t["items"])
        if node["name"] not in seen:
            seen.add(node["name"])
            records.append(
                _RecordDef(
                    name=node["name"],
                    doc=node.get("doc", ""),
                    fields=[_Field(f["name"], f["type"]) for f in node["fields"]],
                )
            )

    visit(schema)
    return records


def collect_enums(schema: dict[str, Any]) -> list[_EnumDef]:
    """Walk a record schema, returning every distinct named enum type used,
    in first-seen order (so generated enum classes precede the dataclasses
    that reference them)."""
    enums: list[_EnumDef] = []
    seen: set[str] = set()

    def visit_type(t: Any) -> None:
        if _is_nullable_union(t):
            visit_type(_union_inner(t))
        elif _is_enum(t):
            if t["name"] not in seen:
                seen.add(t["name"])
                enums.append(_EnumDef(name=t["name"], symbols=list(t["symbols"])))
        elif _is_record(t):
            for field in t["fields"]:
                visit_type(field["type"])
        elif _is_array(t):
            visit_type(t["items"])

    visit_type(schema)
    return enums


def _python_type(t: Any) -> str:
    if t == "string":
        return "str"
    if t == "double":
        return "float"
    if t == "boolean":
        return "bool"
    if _is_decimal(t):
        return "Decimal"
    if _is_timestamp_micros(t):
        return "datetime"
    if _is_enum(t):
        return t["name"]
    if _is_nullable_union(t):
        return f"{_python_type(_union_inner(t))} | None"
    if _is_record(t):
        return t["name"]
    if _is_array(t):
        return f"list[{_python_type(t['items'])}]"
    if _is_map(t):
        return f"dict[str, {_python_type(t['values'])}]"
    raise ValueError(f"unsupported Avro type shape: {t!r}")


def _to_dict_expr(t: Any, value_expr: str) -> str:
    """Python expression converting `value_expr` (already a Python value of
    this field's type) into the plain-dict/scalar shape avro.io.DatumWriter
    expects."""
    if _is_record(t):
        return f"{value_expr}.to_dict()"
    if _is_array(t) and _is_record(t["items"]):
        return f"[_item.to_dict() for _item in {value_expr}]"
    if _is_enum(t):
        return f"{value_expr}.value"
    if _is_nullable_union(t):
        inner = _union_inner(t)
        inner_expr = _to_dict_expr(inner, value_expr)
        if inner_expr == value_expr:
            return value_expr
        return f"({inner_expr} if {value_expr} is not None else None)"
    # str, double, boolean, Decimal, datetime, plain array/map: avro.io
    # accepts these Python types directly (see tools/codegen/README.md).
    return value_expr


def _from_dict_expr(t: Any, value_expr: str) -> str:
    if _is_record(t):
        return f"{t['name']}.from_dict({value_expr})"
    if _is_array(t) and _is_record(t["items"]):
        return f"[{t['items']['name']}.from_dict(_item) for _item in {value_expr}]"
    if _is_enum(t):
        return f"{t['name']}({value_expr})"
    if _is_nullable_union(t):
        inner = _union_inner(t)
        inner_expr = _from_dict_expr(inner, value_expr)
        if inner_expr == value_expr:
            return value_expr
        return f"({inner_expr} if {value_expr} is not None else None)"
    return value_expr


def _uses_type(schema: dict[str, Any], predicate: Any) -> bool:
    for rec in collect_records(schema):
        for f in rec.fields:
            t = f.avro_type
            if _is_nullable_union(t):
                t = _union_inner(t)
            if predicate(t):
                return True
            if _is_array(t) and predicate(t["items"]):
                return True
    return False


def generate_module(schema: dict[str, Any], source_avsc_path: str) -> str:
    records = collect_records(schema)
    enums = collect_enums(schema)
    schema_json_literal = json.dumps(json.dumps(schema, indent=2))

    needs_datetime = _uses_type(schema, _is_timestamp_micros)
    needs_decimal = _uses_type(schema, _is_decimal)

    lines: list[str] = [
        '"""GENERATED -- DO NOT EDIT.',
        "",
        f"Source: {source_avsc_path}",
        "Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here",
        "is silently overwritten on the next regeneration and will be flagged by",
        "the CI drift check before that (contracts/README.md).",
        '"""',
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
    ]
    if enums:
        lines.append("from enum import Enum")
    if needs_datetime:
        lines.append("from datetime import datetime")
    if needs_decimal:
        lines.append("from decimal import Decimal")
    lines.append("from typing import Any")
    lines.append("")
    lines.append(f"SCHEMA_JSON = {schema_json_literal}")
    lines.append('"""The exact source .avsc text, embedded so callers need no filesystem')
    lines.append('path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""')
    lines.append("")

    for enum_def in enums:
        lines.append("")
        lines.append(f"class {enum_def.name}(str, Enum):")
        for symbol in enum_def.symbols:
            lines.append(f'    {symbol} = "{symbol}"')
        lines.append("")

    for rec in records:
        lines.append("")
        lines.append("@dataclass(frozen=True)")
        lines.append(f"class {rec.name}:")
        doc = rec.doc.replace('"""', "'''")
        if doc:
            lines.append(f'    """{doc}"""')
            lines.append("")
        for f in rec.fields:
            lines.append(f"    {f.name}: {_python_type(f.avro_type)}")
        lines.append("")
        lines.append("    def to_dict(self) -> dict[str, Any]:")
        lines.append("        return {")
        for f in rec.fields:
            expr = _to_dict_expr(f.avro_type, f"self.{f.name}")
            lines.append(f'            "{f.name}": {expr},')
        lines.append("        }")
        lines.append("")
        lines.append("    @classmethod")
        lines.append(f'    def from_dict(cls, d: dict[str, Any]) -> {rec.name}:')
        lines.append("        return cls(")
        for f in rec.fields:
            expr = _from_dict_expr(f.avro_type, f'd["{f.name}"]')
            lines.append(f"            {f.name}={expr},")
        lines.append("        )")
        lines.append("")

    return "\n".join(lines) + "\n"
