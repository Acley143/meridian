-- Session 05b: hash-chain support for audit_log (ADR-0008,
-- docs/domain-model.md#auditentry). Forward-only -- V1 is never edited.

-- `seq` is an internal ordering column, not one of AuditEntry's domain
-- fields (same pattern as risk_snapshots.id in V1): the hash chain needs a
-- total, gap-free insertion order to know which row is "previous", and
-- entry_id (an opaque identifier assigned at write time, per the domain
-- model) makes no ordering guarantee on its own.
ALTER TABLE audit_log ADD COLUMN seq BIGINT GENERATED ALWAYS AS IDENTITY;
CREATE UNIQUE INDEX idx_audit_log_seq ON audit_log (seq);

-- Append-only, enforced at the database level (ADR-0008 Task 4): a trigger
-- rejects UPDATE and DELETE outright, for any client/role -- not a REVOKE
-- on the application's own role, since this schema has no role separation
-- set up yet (every table is owned/written by the same connecting user).
-- A trigger enforces the rule regardless of which role issues the
-- statement, which is the stronger and simpler guarantee here.
CREATE OR REPLACE FUNCTION audit_log_reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not permitted (row entry_id=%)',
        TG_OP, COALESCE(OLD.entry_id, 'unknown');
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_reject_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_reject_mutation();

CREATE TRIGGER audit_log_reject_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_reject_mutation();
