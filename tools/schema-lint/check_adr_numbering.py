#!/usr/bin/env python3
"""Verify docs/adr/*.md are contiguously numbered from 0001, no gaps or duplicates."""
import re
import sys
from pathlib import Path

PATTERN = re.compile(r"^(\d{4})-.+\.md$")


def main(argv):
    if len(argv) != 2:
        print("usage: check_adr_numbering.py <adr-dir>", file=sys.stderr)
        return 2

    adr_dir = Path(argv[1])
    numbers = []
    for f in sorted(adr_dir.glob("*.md")):
        m = PATTERN.match(f.name)
        if not m:
            print(f"error: {f.name} does not match NNNN-slug.md", file=sys.stderr)
            return 1
        numbers.append(int(m.group(1)))

    if not numbers:
        print("error: no ADR files found", file=sys.stderr)
        return 1

    seen = set()
    dupes = [n for n in numbers if n in seen or seen.add(n)]
    if dupes:
        print(f"error: duplicate ADR numbers: {sorted(set(dupes))}", file=sys.stderr)
        return 1

    numbers.sort()
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        print(f"error: ADR numbers are not contiguous from 1: got {numbers}", file=sys.stderr)
        return 1

    print(f"OK  {len(numbers)} ADRs, contiguously numbered 0001-{numbers[-1]:04d}, no gaps or duplicates.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
