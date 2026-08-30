#!/usr/bin/env python3
"""Verify every relative markdown link under docs/ resolves to a file that exists."""
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def is_external(target: str) -> bool:
    scheme = urlparse(target).scheme
    return scheme in ("http", "https", "mailto")


def main(argv):
    if len(argv) != 2:
        print("usage: check_markdown_links.py <docs-dir>", file=sys.stderr)
        return 2

    docs_dir = Path(argv[1])
    errors = []
    checked = 0

    for md_file in sorted(docs_dir.rglob("*.md")):
        text = md_file.read_text()
        for match in LINK_PATTERN.finditer(text):
            target = match.group(1).strip()
            if not target or is_external(target):
                continue
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = (md_file.parent / target_path).resolve()
            checked += 1
            if not resolved.exists():
                errors.append(f"{md_file}: broken link '{target}' -> {resolved}")

    if errors:
        print("Broken links:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(f"OK  {checked} relative markdown link(s) under {docs_dir} resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
