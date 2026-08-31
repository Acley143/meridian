"""Cross-language decimal fidelity test (the test this whole contracts
session exists to enable).

Cross-language Decimal divergence is the failure mode ADR-0013 exists to
prevent -- until a test actually pushes bytes between the two language
implementations and checks the value survives, that ADR is an intention,
not a guarantee. This drives contracts/generated/java's
CrossLanguageDecimalTool.java (see java_bridge.py) in both directions:

  Python encodes -> Java decodes -> asserts exact BigDecimal equality
  Java encodes   -> Python decodes -> asserts exact Decimal equality

against RiskSnapshot.price (the field every schema shares the Decimal(38,8)
shape for), using values chosen to break a naive implementation: one not
representable in binary floating point, a negative value, and values at
the precision-38 limit.
"""
import io
from decimal import Decimal
from pathlib import Path

import avro.io
import avro.schema
import pytest
from java_bridge import read_price, write_price
from meridian_contracts.risk_snapshot import SCHEMA_JSON

_SCHEMA = avro.schema.parse(SCHEMA_JSON)

# Chosen to break a naive implementation:
#   - not representable in binary floating point (almost any decimal;
#     0.1 is the canonical example)
#   - a large integer part near the precision-38 limit (38 significant
#     digits total at scale 8: 30 integer digits + 8 fractional)
#   - negative
#   - the smallest representable magnitude at scale 8
#   - exact zero
DECIMAL_CASES = [
    "0.10000000",
    "999999999999999999999999999999.99999999",
    "-999999999999999999999999999999.99999999",
    "-42.00000001",
    "0.00000001",
    "0.00000000",
]


def _sample_risk_snapshot_dict(price: Decimal) -> dict:
    import datetime

    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    return {
        "portfolio_id": "portfolio-1",
        "as_of": now,
        "pricer_version": "0.1.0",
        "price": price,
        "cash_delta": Decimal(0),
        "cash_gamma": Decimal(0),
        "cash_vega": Decimal(0),
        "cash_theta": Decimal(0),
        "cash_rho": Decimal(0),
        "var_95": 0.0,
        "scenario_id": "scenario-1",
        "oldest_input_event_time": now,
        "ingest_time": now,
    }


@pytest.mark.parametrize("decimal_str", DECIMAL_CASES)
def test_python_encodes_java_decodes(decimal_str: str, tmp_path: Path) -> None:
    price = Decimal(decimal_str)
    writer = avro.io.DatumWriter(_SCHEMA)
    buf = io.BytesIO()
    writer.write(_sample_risk_snapshot_dict(price), avro.io.BinaryEncoder(buf))

    out_file = tmp_path / "python_to_java.bin"
    out_file.write_bytes(buf.getvalue())

    result = read_price(out_file, decimal_str)
    assert result.returncode == 0, f"Java rejected Python-encoded bytes:\n{result.stdout}\n{result.stderr}"
    assert "MATCH" in result.stdout


@pytest.mark.parametrize("decimal_str", DECIMAL_CASES)
def test_java_encodes_python_decodes(decimal_str: str, tmp_path: Path) -> None:
    in_file = tmp_path / "java_to_python.bin"
    write_price(decimal_str, in_file)

    reader = avro.io.DatumReader(_SCHEMA)
    decoded = reader.read(avro.io.BinaryDecoder(io.BytesIO(in_file.read_bytes())))

    assert decoded["price"] == Decimal(decimal_str)
