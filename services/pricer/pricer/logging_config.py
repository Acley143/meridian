"""Basic structured-enough logging for `services/pricer`."""
from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def get_logger() -> logging.Logger:
    return logging.getLogger("pricer")
