#!/usr/bin/env python3
"""Validate contracts/openapi/service-api.yaml against the OpenAPI 3 schema."""
import sys

from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename


def main(argv):
    if len(argv) != 2:
        print("usage: check_openapi.py <spec.yaml>", file=sys.stderr)
        return 2

    spec_path = argv[1]
    spec_dict, _base_uri = read_from_filename(spec_path)
    validate(spec_dict)
    print(f"OK  {spec_path} is a valid OpenAPI 3 document.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
