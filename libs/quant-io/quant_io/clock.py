"""The one sanctioned place a wall clock is read on the Python side.

`quant_core` may never call `datetime.now()` (ADR-0010); every stage that
needs `ingest_time` (ADR-0005) reads it from here instead of reaching for
the clock ad hoc.
"""
from datetime import UTC, datetime


def now_utc() -> datetime:
    """The current instant as a timezone-aware UTC `datetime`."""
    return datetime.now(UTC)
