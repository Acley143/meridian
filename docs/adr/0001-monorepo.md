# ADR-0001: Monorepo

## Status
Accepted

## Context
Meridian spans three languages — Python (quant core), Java (service layer), and
TypeScript (dashboard) — sharing a set of data contracts (Avro schemas, OpenAPI)
that are expected to change on a roughly weekly cadence during active development.
A polyrepo split would require each language repo to pin a version of the shared
contracts package and bump it on every change.

## Decision
Meridian is a single monorepo. All languages, services, libraries, contracts, and
infrastructure definitions live in one repository with one commit history.

## Consequences
- A single PR can change a contract and every consumer of it atomically.
- CI must be able to selectively build/test per workstream to stay fast as the
  repo grows; this is deferred until it's actually a problem.
- Ownership boundaries are enforced by convention and `PLAN.md`/`CODEOWNERS`,
  not by repository walls.

## Alternatives considered
- **Polyrepo per language/service.** Rejected: with contracts changing weekly,
  cross-repo version bumps would become the team's primary occupation by the
  third week of the project.
- **Polyrepo with a published contracts package.** Rejected for the same
  reason, plus the added operational cost of running a package registry for a
  five-person student team.
