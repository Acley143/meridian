# infra — Plan

**Owner:** Eng-A  ·  **Quarter:** Q1  ·  **Status:** not started

## Mission
The local dev stack and, eventually, wherever this gets deployed for a demo.
Without this, no other workstream has a Kafka broker, schema registry, or
Postgres to develop against.

## In scope this quarter
- [ ] `docker-compose.yml` at repo root: Kafka, schema registry, Postgres,
      wired with the ports/env every service expects.
- [ ] `make up` / `make setup` targets that bring the stack up from a clean
      checkout.
- [ ] CI workflow (`.github/workflows/ci.yml`) — see root-level CI
      requirements; this workstream owns keeping it green, not necessarily
      every job's content (each workstream owns its own lint/test step).

**Partition counts are set once, at topic creation, and are not a tuning
knob to revisit casually (ADR-0016).** Kafka's default partitioner hashes
a message's key modulo the partition count, so changing partition count on
an already-keyed topic (`ticks`, `risk.snapshots`, `portfolio.state`)
silently redistributes future messages for the same key to a different
partition than past ones — breaking the per-key ordering every consumer of
those topics depends on, with no error anywhere. Whatever topic-creation
step this workstream adds (whether `docker-compose.yml`'s auto-create
defaults or an explicit `kafka-topics --create`) must set the partition
count deliberately up front, not leave it to be adjusted later once real
data exists on the topic.

## Explicitly out of scope
- Terraform/K8s manifests for a real deployment target — `infra/terraform`
  and `infra/k8s` stay empty scaffolding until a workstream actually needs a
  deployed (not just local) environment, per `infra/CLAUDE.md`.
- Any application code.

## Boundaries
- **Owns:** `infra/**`, `docker-compose.yml`, `Makefile`,
  `.github/workflows/ci.yml`.
- **Must not touch:** application code in `libs/`, `services/`, `apps/`
  beyond what's needed to add a lint/test job that calls into it.
- **Depends on:** nothing upstream; every other workstream depends on this
  one being usable from a clean checkout.

## Interfaces
`docker-compose.yml` service names/ports are the interface every other
workstream codes against (e.g. `localhost:9092` for Kafka). Changing a port
or service name is a breaking change to every workstream and should be
flagged as such in the PR.

## Definition of done
- [ ] Deliverables above complete
- [ ] `make setup && make up && make test` succeeds from a clean checkout
- [ ] CI green on a trivial PR
- [ ] Docs updated (root `README.md` quickstart)
- [ ] NFR targets in `docs/nfr-budget.md` — N/A directly; this workstream
      enables measuring them, doesn't itself have a budget line

## Open questions
- Deployment target for a live demo (if any) beyond local Docker Compose —
  Owner: Eng-A, by-when: Q2 planning.

## Forward-looking (not in scope this quarter)
- **Q3: run a real Confluent Schema Registry as a CI service container.**
  `contracts/tests/python/test_schema_evolution.py` currently checks
  `BACKWARD` compatibility by driving Avro's own schema resolution rules
  locally rather than a live registry (see `contracts/README.md`'s
  "Registry stand-in" section for the two specific gaps that leaves: no
  `BACKWARD_TRANSITIVE` check against full history, no subject-naming
  coverage). Acceptable through Q2. Once the local `docker-compose.yml`
  stack (Kafka + schema registry) is proven in Q1/Q2 day-to-day use, add
  the schema registry as a `services:` container in the relevant CI job so
  contract tests can register against and check compatibility with the
  real thing, closing both gaps. Owner: Eng-A, by-when: Q3 planning.

## Session log
(none yet)
