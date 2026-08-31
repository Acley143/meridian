"""Deliberately impure fixture (ADR-0010 enforcement smoke test).

This package exists to prove that the import-linter check enforcing
ADR-0010 can actually fail — a green `.importlinter` run against
`quant_core` alone proves nothing if there is no impure code anywhere for
it to catch. This module imports two I/O-performing packages; CI asserts
that running import-linter against a config covering this package fails.
If this fixture ever passes, the enforcement mechanism itself is broken.

Not part of the `quant_core` distribution: `pyproject.toml`'s
`[tool.setuptools.packages.find]` includes only `quant_core*`, so this
package under `tests/` is never shipped or importable from production code.
"""

import kafka  # type: ignore[import-not-found]  # noqa: F401
import requests  # type: ignore[import-untyped]  # noqa: F401
