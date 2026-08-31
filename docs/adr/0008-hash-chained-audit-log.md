# ADR-0008: Hash-chained audit log

## Status
Accepted

## Context
A risk platform needs a tamper-evident record of what happened — what prices
were computed, what portfolio changes were applied — that can demonstrate its
own integrity without requiring an external ledger or blockchain-scale
infrastructure, which is out of proportion for a five-person student project.

## Decision
The audit log is an append-only table (`AuditEntry`, see
`docs/domain-model.md`). Each row stores the SHA-256 hash of the previous
row's canonical form (a deterministic serialization). This forms a hash
chain: altering or deleting any historical row breaks the chain from that
point forward and is detectable by recomputing hashes forward from any known
row.

## Consequences
- Verifying integrity is a linear scan recomputing
  `SHA-256(canonical(row_n))` and checking it equals `row_{n+1}.prev_hash`,
  expressible as a five-line query/script — no separate infrastructure.
- The canonical form of a row must be defined precisely and stably (field
  order, encoding) or the chain becomes unverifiable across implementations;
  this canonicalization lives alongside the `AuditEntry` schema.
- This is tamper-evident, not tamper-proof: it does not itself prevent a
  privileged actor with database write access from rewriting the whole chain
  from a point forward and recomputing subsequent hashes. It guarantees that
  any unauthorized single-row edit is detectable, which is the stated goal.

## Alternatives considered
- **External/blockchain-anchored ledger.** Rejected: operationally
  disproportionate for a four-quarter student project; a hash chain in a
  normal append-only table gives the same tamper-evidence property for the
  threat model here (detect accidental or unauthorized edits, not defend
  against a compromised database admin).
- **No integrity mechanism, rely on database access controls alone.**
  Rejected: access controls prevent unauthorized writes but don't make an
  authorized-but-wrong edit (e.g. an operator "fixing" a row) detectable.

## Editorial amendments
- 2026-08-31 (Session 05b, core-service): **Honest threat model, stated
  plainly rather than left implicit in the Consequences section's aside.**
  A hash chain detects tampering by anyone who alters a row *without*
  rewriting every subsequent row's `entry_hash`/`prev_hash` chain forward
  from that point. **It does not prevent tampering.** An attacker (or a
  privileged operator, or anyone who otherwise obtains full database write
  access) who is willing to rewrite the whole chain from the tampered row
  forward — updating every downstream `entry_hash`/`prev_hash` to stay
  internally consistent — produces a chain that verifies cleanly end to
  end. Nothing in this table, on its own, distinguishes that rewritten
  chain from a genuine one. Real tamper-evidence against *that* threat
  requires anchoring the head hash (the latest `entry_hash`) somewhere
  outside this database — e.g. periodic external publication to a
  write-once store, a signed log shipped off-host, or a third party that
  observes and records the head hash on a schedule — so a rewritten chain
  disagrees with a previously-published head instead of just disagreeing
  with itself. **This is a real, acknowledged gap, not solved by this
  session or this ADR.** What Session 05b's implementation does provide:
  the append-only database trigger (`V2__audit_log_hash_chain.sql`) raises
  every `UPDATE`/`DELETE` against `audit_log` for *any* client, which
  covers the accidental-edit and honest-mistake case this ADR's own
  Alternatives-considered section already named as in scope — it does not
  and cannot cover a client with the privilege to disable that trigger and
  rewrite forward, which is exactly the gap above.
  - Additionally: `entry_hash`/`prev_hash` cover `entry_id`, `entry_type`,
    and `payload` only (see `docs/domain-model.md#auditentry`'s canonical
    form spec) — `event_time` and `ingest_time` are not part of what's
    hashed. A mutation confined to those two columns does not break the
    chain. Noted here rather than only in the schema doc, since it bears
    directly on what "tamper-evident" actually covers.
