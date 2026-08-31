"""`services/pricer` entrypoint: `python -m pricer.cli <instruments.yaml> [--group-id pricer]`."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from pricer.logging_config import configure_logging, get_logger
from pricer.reference_data import load_reference_data
from pricer.service import PricerService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_data_path", type=Path)
    parser.add_argument("--group-id", default="pricer")
    parser.add_argument(
        "--bootstrap-servers", default=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093")
    )
    parser.add_argument(
        "--schema-registry-url",
        default=os.environ.get("SCHEMA_REGISTRY_URL", "http://localhost:8081"),
    )
    args = parser.parse_args(argv)

    configure_logging()
    log = get_logger()
    reference_data = load_reference_data(args.reference_data_path)
    log.info("loaded reference data from %s", args.reference_data_path)

    service = PricerService(
        bootstrap_servers=args.bootstrap_servers,
        schema_registry_url=args.schema_registry_url,
        reference_data=reference_data,
        tick_group_id=args.group_id,
    )
    service.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
