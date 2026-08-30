# infra

Terraform, Kubernetes manifests, and Docker build definitions for anything
beyond the local dev stack (`docker-compose.yml` at repo root, which is the
day-to-day environment for all other workstreams).

- Per `docs/nfr-budget.md`, there is no availability target — don't over-
  engineer for HA (multi-AZ, autoscaling policies, etc.) this is a student
  project's infra, sized for the load-test numbers in that document, not for
  production resilience.
- `docker-compose.yml` at the repo root is the source of truth for local
  service topology (Kafka, schema registry, Postgres); anything here should
  be consistent with it, not a divergent parallel definition.
- The one mistake most likely here: writing Terraform/K8s for services that
  don't exist yet. Infra for a workstream lands with that workstream's first
  deployable artifact, not speculatively ahead of it.
