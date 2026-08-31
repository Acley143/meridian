"""Puts services/pricer/fixtures on sys.path so test modules (and
pricer_test_helpers.py) can `import loader` regardless of import order --
relying on import-order side effects for this was fragile (ruff's import
sorting alone was enough to break it)."""
import sys
from pathlib import Path

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))
