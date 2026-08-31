"""Approximates the Confluent Schema Registry's BACKWARD compatibility
check without a live registry (none is deployed in CI -- see
.github/workflows/ci.yml's schema-registry-compatibility job and
tools/schema-lint/README.md).

BACKWARD compatibility means: a consumer using the NEW schema can read
data written with the OLD schema. Avro's own schema resolution rules
implement exactly this when you decode with a DatumReader constructed from
(writer_schema=old, reader_schema=new) -- so this module doesn't need to
reimplement the registry's compatibility algorithm, only drive Avro's
existing one: encode a sample instance with the old schema, and see
whether the new schema can decode it. A field present in `new` but not in
`old`'s encoded bytes resolves successfully only if it has a default;
otherwise Avro raises during decode, exactly matching what BACKWARD is
supposed to reject.
"""
import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import avro.io
import avro.schema


def _sample_value(avro_type: Any) -> Any:
    """A structurally-valid filler value for any field type used in
    contracts/avro/*.avsc, for encoding a "some old record" instance."""
    if avro_type == "string":
        return "sample"
    if avro_type == "double":
        return 0.0
    if avro_type == "boolean":
        return False
    if isinstance(avro_type, dict):
        if avro_type.get("logicalType") == "decimal":
            return Decimal(0)
        if avro_type.get("logicalType") == "timestamp-micros":
            return datetime(2026, 1, 1, tzinfo=timezone.utc)
        if avro_type.get("type") == "record":
            return _sample_record(avro_type)
        if avro_type.get("type") == "array":
            return []
        if avro_type.get("type") == "map":
            return {}
    raise ValueError(f"backward_compat._sample_value: unsupported type {avro_type!r}")


def _sample_record(schema: dict) -> dict:
    return {f["name"]: _sample_value(f["type"]) for f in schema["fields"]}


def is_backward_compatible(old_schema: dict, new_schema: dict) -> tuple[bool, str]:
    """Returns (compatible, detail). `detail` carries the resolution error
    message on incompatibility, empty string on compatibility."""
    old_parsed = avro.schema.parse(_json_dumps(old_schema))
    new_parsed = avro.schema.parse(_json_dumps(new_schema))

    buf = io.BytesIO()
    avro.io.DatumWriter(old_parsed).write(_sample_record(old_schema), avro.io.BinaryEncoder(buf))
    buf.seek(0)

    try:
        avro.io.DatumReader(old_parsed, new_parsed).read(avro.io.BinaryDecoder(buf))
    except Exception as e:  # noqa: BLE001 -- any decode failure means "incompatible"
        return False, str(e)
    return True, ""


def _json_dumps(schema: dict) -> str:
    import json

    return json.dumps(schema)
