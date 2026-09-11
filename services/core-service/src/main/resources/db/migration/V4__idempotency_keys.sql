-- Session P: idempotency store for POST /trades (ADR-0023). Forward-only --
-- V1/V2/V3 are never edited.
--
-- One row per (endpoint, idempotency_key) claim. The endpoint is part of
-- the key so a client-supplied Idempotency-Key reused across /trades and a
-- future /portfolios cannot collide -- two unrelated endpoints hashing the
-- same key are not the same request.
--
-- response_status/response_body are nullable at insert time: the claiming
-- request INSERTs this row (empty response columns) before it does any
-- business work, then UPDATEs the same row with the real response once one
-- exists, all inside the one @Transactional applyTradeIdempotent call.
-- The PRIMARY KEY is the concurrency mechanism itself (ADR-0023) -- a
-- second INSERT for the same (endpoint, idempotency_key) blocks on this
-- row's lock until the first transaction commits or rolls back, then
-- either fails the unique check (row now exists, safe to read and decide
-- replay/409) or succeeds outright (the first request rolled back, the key
-- is free again).
CREATE TABLE idempotency_keys (
    endpoint            TEXT NOT NULL,
    idempotency_key     TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    response_status     INTEGER,
    response_body       TEXT,
    created_at          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (endpoint, idempotency_key)
);

-- Backs the 24-hour retention sweep (services/core-service/PLAN.md open
-- questions) -- not built in this session, tracked as follow-up only.
-- Deliberately NOT used to filter lookups: an expired-but-unswept row must
-- still collide on INSERT and still be found on lookup, or the insert
-- would fail the unique check while the lookup finds nothing to replay,
-- producing an error path with no stored response (ADR-0023).
CREATE INDEX idx_idempotency_keys_created_at ON idempotency_keys (created_at);
