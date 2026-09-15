"""Explicit Avro <-> OpenAPI pairing map for check_cross_contract.py (ADR-0026).

Closed-world by construction: every Avro record and every OpenAPI
components/schemas entry must appear exactly once below, either in PAIRS or
in one of the two UNPAIRED maps, each with a reason. check_cross_contract.py
fails on any schema found on either side that is absent from this file --
see ADR-0026's rationale for why silent coverage of unrecognised schemas is
not acceptable here.

This file is data only. It does not import contracts, walk any schema, or
run any check itself -- that is check_cross_contract.py's job.
"""

# Each pair names one Avro record and the OpenAPI components/schemas entry
# it must agree with, field-for-field, per the rules in ADR-0026.
#
# avro_file: the .avsc file the record is defined in (Position is nested
# inside portfolio-state.avsc's positions array, not its own file).
# avro_record: the Avro record's "name".
# openapi_component: the key under components/schemas.
PAIRS = [
    {
        "avro_file": "portfolio-state.avsc",
        "avro_record": "Position",
        "openapi_component": "Position",
    },
    {
        "avro_file": "reference-instruments.avsc",
        "avro_record": "ReferenceInstrument",
        "openapi_component": "Instrument",
    },
    {
        "avro_file": "risk-snapshot.avsc",
        "avro_record": "RiskSnapshot",
        "openapi_component": "RiskSnapshot",
    },
]

# Avro records with no OpenAPI counterpart, and why.
UNPAIRED_AVRO = {
    "PortfolioStateKey": (
        "Kafka message key; keys never cross into OpenAPI by construction."
    ),
    "ReferenceInstrumentKey": (
        "Kafka message key; keys never cross into OpenAPI by construction."
    ),
    "RiskSnapshotKey": (
        "Kafka message key; keys never cross into OpenAPI by construction."
    ),
    "TickKey": (
        "Kafka message key; keys never cross into OpenAPI by construction."
    ),
    "PortfolioState": (
        "The envelope is Kafka-internal materialisation. Only its positions "
        "slice is exposed over REST, and that slice is separately paired "
        "as Position, above."
    ),
    "Tick": (
        "market.ticks goes ingest -> pricer over Kafka and is never "
        "surfaced through core-service's REST API."
    ),
}

# OpenAPI components/schemas entries with no Avro counterpart, and why.
UNPAIRED_OPENAPI = {
    "Portfolio": (
        "Portfolio IDENTITY (name, base_currency, owner). Despite the name, "
        "this is NOT the REST counterpart of Avro PortfolioState, which "
        "carries positions over time and none of these fields. Different "
        "domain objects with similar names -- deliberately not paired."
    ),
    "PortfolioRequest": "REST-only creation input; no wire event of its own.",
    "InstrumentRequest": "REST-only creation input; no wire event of its own.",
    "TradeRequest": "REST-only creation input; no wire event of its own.",
    "Trade": (
        "No per-trade Avro message exists: ADR-0003 republishes full "
        "portfolio state after a trade rather than emitting a "
        "trade-level event."
    ),
    "AuditEntry": "The audit log is Postgres-only per ADR-0008; never published.",
}
