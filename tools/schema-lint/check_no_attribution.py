#!/usr/bin/env python3
"""Verify no commit reachable from HEAD contains a Co-Authored-By trailer or
a "Generated with Claude Code" line.
"""
import re
import subprocess
import sys

FORBIDDEN = re.compile(r"co-authored-by|generated with claude code", re.IGNORECASE)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main():
    log = git("log", "--format=%H%n%B%n---END---")
    violations = []
    commit = None
    body_lines = []
    for line in log.splitlines():
        if line == "---END---":
            body = "\n".join(body_lines)
            if FORBIDDEN.search(body):
                violations.append(commit)
            commit = None
            body_lines = []
        elif commit is None:
            commit = line
        else:
            body_lines.append(line)

    if violations:
        print("Commits with a forbidden attribution trailer/line:", file=sys.stderr)
        for c in violations:
            print(f"  {c}", file=sys.stderr)
        return 1

    print("OK  no Co-Authored-By trailer or 'Generated with Claude Code' line found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
