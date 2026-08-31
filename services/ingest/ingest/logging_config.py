"""Structured logging with `scenario_id` on every line.

When something is wrong three components downstream of ingest, the first
question is which scenario produced the bad data — so every log line this
service emits carries `scenario_id`, not just the ones that happen to be
about a scenario.
"""
from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s scenario_id=%(scenario_id)s %(message)s",
    )


def get_scenario_logger(scenario_id: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger("ingest"), {"scenario_id": scenario_id})
