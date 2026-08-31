-- Session 05d: GET /portfolios/{id}/audit needs to filter audit_log by
-- portfolio -- nothing in the table (or in AuditEntry itself,
-- docs/domain-model.md#auditentry) carries that today. AuditEntry's own
-- wire schema deliberately has no portfolio_id (not every audit entry
-- type is portfolio-scoped, e.g. a future instrument-creation entry), so
-- this column is a server-side filtering aid only, not part of the
-- canonical form (CanonicalForm.java) and not part of the REST response
-- shape (contracts/openapi/service-api.yaml's AuditEntry schema is
-- unchanged) -- it is never hashed and never serialized back to a client.
ALTER TABLE audit_log ADD COLUMN portfolio_id TEXT;

CREATE INDEX idx_audit_log_portfolio_id ON audit_log (portfolio_id, event_time DESC)
    WHERE portfolio_id IS NOT NULL;
