-- Initial schema for core-service (Session 05a, ADR-0004, ADR-0005,
-- ADR-0007, ADR-0013, ADR-0019). Forward-only: this and every future
-- migration in this directory are never edited once merged -- a later
-- change is always a new Vn__*.sql file.
--
-- Money/quantity columns are NUMERIC(38,8), matching ADR-0013's
-- precision/scale exactly, so no rounding happens at the database
-- boundary that isn't already accounted for by BigDecimal on the Java
-- side. Every timestamp is TIMESTAMPTZ, stored UTC, per ADR-0005.

-- instruments: core-service's system of record for Instrument
-- (docs/domain-model.md#instrument). core-service is the sole producer of
-- reference.instruments (ADR-0019); this table is what it publishes from.
-- Per the domain model, a changed strike/expiry is a new instrument, not
-- an update to an existing row -- rows here are inserted, not mutated.
CREATE TABLE instruments (
    instrument_id   TEXT PRIMARY KEY,
    underlying_id   TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    option_type     TEXT,
    strike          NUMERIC(38, 8),
    expiry          TIMESTAMPTZ,
    currency        TEXT NOT NULL,
    contract_size   NUMERIC(38, 8) NOT NULL
);

-- portfolios: docs/domain-model.md#portfolio. Static/slow-changing
-- metadata; positions live in `positions` below, not here.
CREATE TABLE portfolios (
    portfolio_id  TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    base_currency TEXT NOT NULL,
    owner         TEXT NOT NULL
);

-- positions: docs/domain-model.md#position. Derived state -- exists
-- because trades happened, not itself independently mutated by a client;
-- core-service folds trades into positions internally. One row per
-- (portfolio_id, instrument_id): the "latest applied trade" state, not a
-- history (trades below is the append-only history).
CREATE TABLE positions (
    portfolio_id      TEXT NOT NULL REFERENCES portfolios (portfolio_id),
    instrument_id     TEXT NOT NULL REFERENCES instruments (instrument_id),
    quantity          NUMERIC(38, 8) NOT NULL,
    average_cost      NUMERIC(38, 8) NOT NULL,
    as_of_event_time  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (portfolio_id, instrument_id)
);

CREATE INDEX idx_positions_portfolio_id ON positions (portfolio_id);

-- trades: docs/domain-model.md#trade. Immutable, append-only source of
-- truth -- positions are a fold over trades. Never updated or deleted; a
-- correction is a new trade with an offsetting entry.
CREATE TABLE trades (
    trade_id      TEXT PRIMARY KEY,
    portfolio_id  TEXT NOT NULL REFERENCES portfolios (portfolio_id),
    instrument_id TEXT NOT NULL REFERENCES instruments (instrument_id),
    quantity      NUMERIC(38, 8) NOT NULL,
    price         NUMERIC(38, 8) NOT NULL,
    event_time    TIMESTAMPTZ NOT NULL,
    ingest_time   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_trades_portfolio_id ON trades (portfolio_id);

-- risk_snapshots: docs/domain-model.md#risksnapshot. Identity is the
-- ADR-0007 tuple (portfolio_id, as_of, pricer_version) -- enforced here
-- by a real UNIQUE constraint, not just an index, so it can back an
-- `ON CONFLICT` upsert and so the database rejects a duplicate even if
-- application code somewhere forgets to dedupe. var_95 is float64
-- (DOUBLE PRECISION) per ADR-0004 -- a risk statistic, not a cash amount,
-- even though its unit is currency. Every other cash field, including
-- the cash Greeks (ADR-0017), is NUMERIC(38, 8).
CREATE TABLE risk_snapshots (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id            TEXT NOT NULL REFERENCES portfolios (portfolio_id),
    as_of                   TIMESTAMPTZ NOT NULL,
    pricer_version          TEXT NOT NULL,
    price                   NUMERIC(38, 8) NOT NULL,
    cash_delta              NUMERIC(38, 8) NOT NULL,
    cash_gamma              NUMERIC(38, 8) NOT NULL,
    cash_vega               NUMERIC(38, 8) NOT NULL,
    cash_theta              NUMERIC(38, 8) NOT NULL,
    cash_rho                NUMERIC(38, 8) NOT NULL,
    var_95                  DOUBLE PRECISION NOT NULL,
    scenario_id             TEXT NOT NULL,
    oldest_input_event_time TIMESTAMPTZ NOT NULL,
    ingest_time             TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_risk_snapshots_identity UNIQUE (portfolio_id, as_of, pricer_version)
);

CREATE INDEX idx_risk_snapshots_portfolio_as_of ON risk_snapshots (portfolio_id, as_of);

-- audit_log: docs/domain-model.md#auditentry, ADR-0008. Schema only this
-- session -- the hash-chain write/verify application code is Session 05b.
-- Append-only by convention here; enforced at the database level in 05b
-- (a trigger rejecting UPDATE/DELETE), not by this migration.
CREATE TABLE audit_log (
    entry_id    TEXT PRIMARY KEY,
    entry_type  TEXT NOT NULL,
    payload     TEXT NOT NULL,
    prev_hash   TEXT NOT NULL,
    entry_hash  TEXT NOT NULL,
    event_time  TIMESTAMPTZ NOT NULL,
    ingest_time TIMESTAMPTZ NOT NULL
);
