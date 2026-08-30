# Rotation

Who owns which surface, per quarter. Five people, four quarters. Names below
are role placeholders (`Eng-A`...`Eng-E`) — replace with actual team member
names in the first PR against this file; the rotation structure itself is
the part settled here.

Ownership here is advisory for review routing, not a hard gate — the hard
gate is `CODEOWNERS` and each workstream's `PLAN.md` **Boundaries** section.

## Q1 — Black-Scholes pricer, simulated feed, service/schema skeleton

| Surface | Owner |
|---|---|
| `contracts/`, `docs/domain-model.md` | Eng-A |
| `libs/quant-core`, `libs/quant-io` | Eng-B |
| `services/pricer` | Eng-B |
| `services/ingest` | Eng-C |
| `services/core-service` | Eng-D |
| `apps/dashboard` | Eng-E |
| `infra/`, CI | Eng-A |

## Q2 — American options, portfolio VaR, audit log

| Surface | Owner |
|---|---|
| `libs/quant-core` (American pricers, VaR) | Eng-B |
| `services/pricer` (portfolio aggregation) | Eng-C |
| `services/core-service` (audit log, ADR-0008) | Eng-D |
| `apps/dashboard` (VaR views) | Eng-E |
| `infra/`, CI | Eng-A |

## Q3 — Monte Carlo, correlated portfolio risk, load testing prep

| Surface | Owner |
|---|---|
| `libs/quant-core` (Monte Carlo, ADR-0006) | Eng-A |
| `services/pricer` (correlated VaR) | Eng-B |
| `services/core-service` | Eng-C |
| `apps/dashboard` | Eng-D |
| `infra/`, load-test harness | Eng-E |

## Q4 — Hardening, load testing, NFR verification

All hands against `docs/nfr-budget.md`. Rotation dissolves into whichever
budget line is failing; the last owner of a surface is first point of
contact for issues in it. Load test execution and sign-off: Eng-E.

## Updating this file

Rotation changes (a person moving surfaces mid-quarter) are a normal PR
against this file, not an ADR — this is a staffing decision, not an
architectural one.
