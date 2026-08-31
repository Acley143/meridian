#!/usr/bin/env python3
"""Verify only quant_core/numeric.py calls float()/Decimal() in libs/quant-core.

Per ADR-0013 and libs/quant-core Task 2, the Decimal<->float64 conversion
that happens at the money/model boundary is the single most likely source
of a cross-language divergence, so it happens in exactly one place:
quant_core.numeric (to_model / to_money). No other module may call float()
or Decimal() directly on a boundary value — this is import-linter's blind
spot (it checks imports, not calls), so it is enforced here instead.
"""
import ast
import sys
from pathlib import Path

ALLOWED_RELATIVE_PATH = "numeric.py"
BANNED_CALLS = {"float", "Decimal"}


def find_violations(root: Path) -> list[str]:
    violations = []
    for path in sorted(root.rglob("*.py")):
        if path.name == ALLOWED_RELATIVE_PATH:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in BANNED_CALLS
            ):
                violations.append(f"{path}:{node.lineno}: bare {node.func.id}() call")
    return violations


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_quant_core_boundary.py <path to quant_core package>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1])
    violations = find_violations(root)

    if violations:
        print("Decimal/float boundary violations (only numeric.py may do this conversion):", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("OK  no bare float()/Decimal() calls outside quant_core/numeric.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
