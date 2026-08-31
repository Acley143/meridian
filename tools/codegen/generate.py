#!/usr/bin/env python3
"""Single entry point for contracts codegen (`make gen`, ADR-0015).

Generates Python dataclass bindings and Java POJOs from every
`contracts/avro/*.avsc`, deterministically: same schema files in,
byte-identical files out (given the same pinned generator versions --
`avro-java-codegen/pom.xml` pins `avro-maven-plugin`; this script's own
Python codegen has no external version to pin).

Usage:
    python3 tools/codegen/generate.py contracts/
    python3 tools/codegen/generate.py contracts/ --python-out DIR --java-out DIR

The two `--*-out` flags exist for the CI drift check (contracts/README.md):
regenerate into a temp directory and diff against what's committed, rather
than regenerating in place and hoping a reviewer notices an uncommitted
diff. Default output locations are the real, checked-in ones.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from avro_to_python import generate_module  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PYTHON_OUT = _REPO_ROOT / "contracts" / "generated" / "python" / "meridian_contracts"
_DEFAULT_JAVA_OUT = _REPO_ROOT / "contracts" / "generated" / "java" / "src" / "main" / "java"
_JAVA_CODEGEN_POM = _REPO_ROOT / "tools" / "codegen" / "avro-java-codegen" / "pom.xml"
_JAVA_CODEGEN_TARGET = (
    _REPO_ROOT / "tools" / "codegen" / "avro-java-codegen" / "target" / "generated-sources" / "avro"
)

_JAVA_BANNER = (
    "// GENERATED -- DO NOT EDIT.\n"
    "// Source: {source}\n"
    "// Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here\n"
    "// is silently overwritten on the next regeneration and will be flagged by\n"
    "// the CI drift check before that (contracts/README.md).\n\n"
)


def _module_name(avsc_path: Path) -> str:
    return avsc_path.stem.replace("-", "_")


def generate_python(avro_dir: Path, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    module_names = []
    for avsc_path in sorted(avro_dir.glob("*.avsc")):
        schema = json.loads(avsc_path.read_text())
        module_name = _module_name(avsc_path)
        module_names.append(module_name)
        source_ref = f"contracts/avro/{avsc_path.name}"
        code = generate_module(schema, source_ref)
        (out_dir / f"{module_name}.py").write_text(code)

    init_lines = [
        '"""GENERATED -- DO NOT EDIT. Regenerate via `make gen`."""',
        "",
    ]
    for name in sorted(module_names):
        init_lines.append(f"from . import {name} as {name}")
    (out_dir / "__init__.py").write_text("\n".join(init_lines) + "\n")


def generate_java(avro_dir: Path, out_dir: Path) -> None:
    if _JAVA_CODEGEN_TARGET.exists():
        shutil.rmtree(_JAVA_CODEGEN_TARGET)

    result = subprocess.run(
        ["mvn", "-q", "-f", str(_JAVA_CODEGEN_POM), "generate-sources"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit("avro-maven-plugin codegen failed (see output above)")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    for java_file in sorted(_JAVA_CODEGEN_TARGET.rglob("*.java")):
        rel = java_file.relative_to(_JAVA_CODEGEN_TARGET)
        avsc_name = _avsc_name_for_class(rel.stem, avro_dir)
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        banner = _JAVA_BANNER.format(source=f"contracts/avro/{avsc_name}")
        dest.write_text(banner + java_file.read_text())


def _avsc_name_for_class(class_name: str, avro_dir: Path) -> str:
    """Best-effort: find which .avsc top-level record name matches this
    generated class (nested records like Position map to their parent's
    file; not worth a precise reverse-index for a banner comment)."""
    for avsc_path in sorted(avro_dir.glob("*.avsc")):
        schema = json.loads(avsc_path.read_text())
        if schema.get("name") == class_name:
            return avsc_path.name
        for field in schema.get("fields", []):
            t = field["type"]
            if isinstance(t, dict) and t.get("name") == class_name:
                return avsc_path.name
            if (
                isinstance(t, dict)
                and t.get("type") == "array"
                and isinstance(t.get("items"), dict)
                and t["items"].get("name") == class_name
            ):
                return avsc_path.name
    return "contracts/avro/ (unknown source)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contracts_dir", type=Path)
    parser.add_argument("--python-out", type=Path, default=_DEFAULT_PYTHON_OUT)
    parser.add_argument("--java-out", type=Path, default=_DEFAULT_JAVA_OUT)
    parser.add_argument("--skip-java", action="store_true", help="Python only (faster local iteration).")
    args = parser.parse_args()

    avro_dir = args.contracts_dir / "avro"

    generate_python(avro_dir, args.python_out)
    print(f"OK  Python bindings -> {args.python_out}")

    if not args.skip_java:
        generate_java(avro_dir, args.java_out)
        print(f"OK  Java bindings -> {args.java_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
