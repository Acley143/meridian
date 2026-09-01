#!/usr/bin/env python3
"""Verify apps/dashboard/src contains no absolute URL pointing at the
core-service host/port (ADR-0020) -- the dashboard must issue only
same-origin requests, proxied in dev by apps/dashboard/vite.config.ts.
"""
import re
import sys
from pathlib import Path

FORBIDDEN = re.compile(r"http://localhost:8080|127\.0\.0\.1:8080|(?<![\w.]):8080")


def main(argv):
    if len(argv) != 2:
        print("usage: check_dashboard_same_origin.py <dashboard-src-dir>", file=sys.stderr)
        return 2

    src_dir = Path(argv[1])
    violations = []
    for f in sorted(src_dir.rglob("*")):
        if not f.is_file() or f.suffix not in (".ts", ".tsx", ".js", ".jsx"):
            continue
        for lineno, line in enumerate(f.read_text().splitlines(), start=1):
            if FORBIDDEN.search(line):
                violations.append(f"{f}:{lineno}: {line.strip()}")

    if violations:
        print("Absolute core-service URLs found under apps/dashboard/src (ADR-0020 violation):", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("OK  no absolute core-service URL found under apps/dashboard/src.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
