"""`services/ingest` entrypoint: `python -m ingest.cli <scenario.yaml> [--pacing realtime|replay]`."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from quant_io.tick_producer import TickProducer

from ingest.feed import PacingMode, run_feed
from ingest.logging_config import configure_logging, get_scenario_logger
from ingest.scenario import load_scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_path", type=Path)
    parser.add_argument(
        "--pacing", choices=[m.value for m in PacingMode], default=PacingMode.REALTIME.value
    )
    parser.add_argument(
        "--bootstrap-servers", default=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093")
    )
    parser.add_argument(
        "--schema-registry-url",
        default=os.environ.get("SCHEMA_REGISTRY_URL", "http://localhost:8081"),
    )
    args = parser.parse_args(argv)

    configure_logging()
    scenario = load_scenario(args.scenario_path)
    log = get_scenario_logger(scenario.scenario_id)
    log.info("loaded scenario from %s", args.scenario_path)

    producer = TickProducer(
        bootstrap_servers=args.bootstrap_servers,
        schema_registry_url=args.schema_registry_url,
    )
    run_feed(scenario, producer, PacingMode(args.pacing), logger=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
