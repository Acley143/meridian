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
