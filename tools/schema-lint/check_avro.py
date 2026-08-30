#!/usr/bin/env python3
"""Validate that every .avsc under a directory parses as JSON and that any
decimal logical type field declares explicit precision and scale (ADR-0013).
"""
import json
import sys
from pathlib import Path


def check_decimal_fields(node, path):
    errors = []
    if isinstance(node, dict):
        if node.get("logicalType") == "decimal":
            if "precision" not in node or "scale" not in node:
                errors.append(f"{path}: decimal logicalType missing explicit precision/scale (ADR-0013)")
        for key, value in node.items():
            errors.extend(check_decimal_fields(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            errors.extend(check_decimal_fields(item, f"{path}[{i}]"))
    return errors


def main(argv):
    if len(argv) != 2:
        print("usage: check_avro.py <avro-dir>", file=sys.stderr)
        return 2

    avro_dir = Path(argv[1])
    files = sorted(avro_dir.glob("*.avsc"))
    if not files:
        print(f"no .avsc files found under {avro_dir}", file=sys.stderr)
        return 2

    all_errors = []
    for f in files:
        try:
            schema = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            all_errors.append(f"{f}: invalid JSON: {e}")
            continue
        errors = check_decimal_fields(schema, f.name)
        all_errors.extend(errors)
        print(f"OK  {f}")

    if all_errors:
        print("\nErrors:", file=sys.stderr)
        for e in all_errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(f"\n{len(files)} schema(s) valid, all decimal fields declare precision+scale.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
