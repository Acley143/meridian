-- ADR-0028 Decision 6: a risk snapshot records the reporting currency its
-- figures are denominated in. Forward-only -- V1 to V4 are never edited.
--
-- NOT NULL with an empty-string default, deliberately not a guessed currency:
-- every row that exists when this migration runs was written before the
-- field existed, so its currency is genuinely unknown, and the empty string
-- is the same "unknown" value contracts/avro/risk-snapshot.avsc uses as its
-- compatibility default. Nothing here may backfill USD -- ADR-0028 Decision 2
-- forbids assuming a currency. New rows are written by the upsert with the
-- pricer's real value, which the pricer never leaves empty.
ALTER TABLE risk_snapshots
    ADD COLUMN base_currency TEXT NOT NULL DEFAULT '';
