#!/usr/bin/env python3
"""Every path in the OpenAPI spec must live under /api/v1 (ADR-0021).

The dashboard's dev proxy routes a single /api entry (ADR-0020); a path
added at any other root bypasses the proxy and falls through to Vite's SPA
fallback (index.html/200) instead of erroring. This check is what makes
ADR-0021's "structurally impossible" claim actually true.
"""
import sys

import yaml

PREFIX = "/api/v1"


def main(argv):
    if len(argv) != 2:
        print("usage: check_api_v1_prefix.py <spec.yaml>", file=sys.stderr)
        return 2

    spec_path = argv[1]
    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    paths = spec.get("paths", {})
    if not paths:
        print(f"no paths found under {spec_path}", file=sys.stderr)
        return 2

    offenders = [p for p in paths if not p.startswith(PREFIX + "/") and p != PREFIX]

    if offenders:
        print(f"\nErrors: paths not under {PREFIX} (ADR-0021):", file=sys.stderr)
        for p in offenders:
            print(f"  {p}", file=sys.stderr)
        return 1

    print(f"OK  {len(paths)} path(s), all under {PREFIX}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
