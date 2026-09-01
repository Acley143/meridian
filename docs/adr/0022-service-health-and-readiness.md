# ADR-0022: Service health and readiness

## Status
Accepted

## Context
`services/core-service` has no way to answer "is this instance up and able
to serve?" without issuing a business request and interpreting the result.
It carries no `spring-boot-starter-actuator` dependency and no health
controller (confirmed: no dependency in `pom.xml`, no health endpoint,
`GET /actuator/health` 404s against the running service — see ADR-0021's
own Consequences section, which already named this gap while explaining why
`server.servlet.context-path` was rejected).

An unhealthy service that returns nothing is indistinguishable from a
healthy service with no data — this project's characteristic failure shape
(the same motivation behind `oldest_input_event_time` on the dashboard).
At the infrastructure layer it shows up as: nothing can safely restart or
load-balance around a broken instance, because nothing can tell a broken
instance from an idle one. Q3's deployment work needs real probes and
cannot retrofit them without another pass through this service.

`core-service` also has no `Dockerfile` and no entry in `docker-compose.yml`
today — it runs as a local Maven/Spring Boot process against
`localhost:5432`/`localhost:9093`/`localhost:8081` by default. This ADR adds
the probes; it does not containerize the service. See Consequences.

### ADR-0018's use of "readiness"
ADR-0018 ("Readiness gates and price cache recovery") uses "readiness" for a
different concept: a Kafka *consumer* (the pricer) reporting itself ready
only once its derived state — compacted views, the price cache — has fully
hydrated by reading its input streams, and suppressing all output until
then. That is about *when a consumer starts emitting*, decided entirely from
the consumer's own replay progress.

This ADR's "readiness" is a Spring Boot Actuator HTTP probe consulted by an
external orchestrator (a load balancer, a compose healthcheck) to decide
*whether to route traffic to this instance*, decided from the instance's own
ability to serve reads right now. The two are related in spirit — both
exist so a component that cannot yet do its job says so instead of silently
producing wrong or absent output — but they are different mechanisms guarding
different transitions in different processes. `core-service` has no
hydration phase in ADR-0018's sense (it is not a derived-state Kafka
consumer feeding a cache; its REST reads go straight to Postgres), so the
two ADRs do not conflict and do not need to share an implementation. This
section exists so the shared word is never read as one meaning bleeding
into the other.

## Decision

### Liveness and readiness are different things
- **Liveness** (`GET /actuator/health/liveness`) answers "is the process
  alive and is its event loop not wedged?" It depends on nothing external —
  not Postgres, not Kafka. A liveness check that fails on a database blip
  causes an orchestrator to restart every replica simultaneously, turning a
  recoverable dependency outage into a self-inflicted restart storm.
- **Readiness** (`GET /actuator/health/readiness`) answers "can this
  instance serve correct responses right now?" Failing readiness removes an
  instance from the load balancer; it does not restart it.

Both are exposed via Spring Boot's availability probes
(`management.endpoint.health.probes.enabled: true`), which register
`livenessState`/`readinessState` indicators and the `liveness`/`readiness`
groups.

### Readiness gates on Postgres, not on Kafka
Postgres is load-bearing for the REST read path (`GET
/api/v1/portfolios/{id}/...`) — without it, reads fail, so `NotReady` is the
honest answer. The auto-configured `DataSourceHealthIndicator` (id `db`) is
added explicitly to the `readiness` group in `application.yml`
(`management.endpoint.health.group.readiness.include: readinessState, db`)
— it is not enough for `db` to merely exist on the aggregate
`/actuator/health`; it must be a member of the group Kubernetes-style probes
actually query.

Kafka is deliberately excluded. `core-service`'s REST reads are served
entirely from Postgres, so a dead or rebalancing `risk.snapshots` consumer
leaves reads working, only stale — and the dashboard already renders
staleness via `oldest_input_event_time`. Gating readiness on consumer state
would pull the instance from traffic during a rebalance, a replay, or a
broker blip, trading a degraded read for an absent one, which is worse.
Kafka consumer state is reported as a health-body **detail** —
`RiskSnapshotConsumerHealthIndicator`, appearing under
`/actuator/health`'s `riskSnapshotConsumer` component — but that indicator's
bean id is never added to the readiness group's `include`. A silently dead
consumer therefore remains an observability gap, not a readiness signal;
that gap is real and is tracked as open Q2 work below, not solved here.

`core-service`'s Kafka consumption is a hand-rolled `KafkaConsumer` driven
by a manual poll loop (`RiskSnapshotConsumerRunner`/
`RiskSnapshotConsumerService`), not Spring Kafka's `@KafkaListener`/
`MessageListenerContainer`. `KafkaConsumer` is not thread-safe, and a health
indicator runs on an HTTP request thread, not the poll loop's thread — so
`RiskSnapshotConsumerHealthIndicator` never touches the consumer directly.
`RiskSnapshotConsumerRunner` publishes an `AtomicReference` (partition
assignment) and a `volatile long` (last-poll-completed timestamp) from
inside its own poll loop, immediately after each `pollOnce()` returns; the
indicator only reads those. A poll that returns zero records still
completed successfully — the published timestamp proves the loop is alive,
it is **not** a data-freshness signal, and is not conflated with
`oldest_input_event_time`. The indicator reports the raw timestamp and its
derived age and lets a human (or a future alert) judge what's too old; it
does not bake a staleness threshold into itself, since a threshold there is
a readiness gate wearing a different hat — precisely what this ADR rejects.

**A verified limitation, not silently assumed:** hand-testing against a
real broker outage (stopping the `kafka` container in `docker-compose.yml`
while `core-service` ran locally) showed that `KafkaConsumer.poll()` does
not throw when the broker is unreachable — it logs `Connection to node N
could not be established` and returns an empty batch. The poll loop
correctly treats that as a successful poll by the definition above, so
`lastPollAgeMillis` does **not** grow during a real single-broker outage;
the detail cannot currently distinguish "broker down" from "broker up, idle."
Detecting broker reachability specifically (versus loop liveness) would need
a different signal — e.g. consumer metrics or a separate admin-client probe
— and is left for the same Q2 observability work as consumer-death
detection, rather than folded into this session as an unplanned addition.

### Exposure
Only `health` is exposed
(`management.endpoints.web.exposure.include: health`). `env`, `beans`,
`heapdump`, `threaddump`, `configprops`, `loggers`, and everything else
actuator ships stay unexposed — confirmed by request
(`GET /actuator/env` → 404) rather than assumed from configuration alone.
`show-details: always` is set so the readiness/health bodies actually show
the `db`/`riskSnapshotConsumer` contributions this ADR relies on being
visible; there is no other client of this actuator surface and no
authentication layer in front of it to gate `show-details` behind.

### Actuator stays outside `/api/v1`
Per ADR-0021, `/api/v1` is reserved for the surface defined in
`contracts/openapi/service-api.yaml`. Actuator paths are not added to that
spec and carry no `/api/v1` prefix — this is exactly the case ADR-0021's
own Consequences section anticipated ("Anything Spring-managed outside
`contracts/openapi/service-api.yaml`'s surface — actuator, if it is ever
added — stays at the root, unversioned and unprefixed, by construction").

## Consequences
- A Postgres outage now produces an honest, machine-readable `NotReady`
  instead of failed business requests with no structural signal; a Kafka
  outage produces no readiness change at all, by design.
- Nothing in this repository consumes these probes yet.
  `services/core-service` has no `Dockerfile` and no entry in
  `docker-compose.yml` (it is a local process, not a compose service) — so
  there is no compose `healthcheck:`/`depends_on: condition:` to point at
  readiness, and nothing else in `docker-compose.yml` has a healthcheck
  either (`postgres`, `kafka`, `schema-registry` are all healthcheck-less
  today; `schema-registry`'s `depends_on: kafka` carries no `condition:`,
  so it starts against a possibly-not-yet-ready broker). Containerizing
  `core-service` — base image, JVM flags, layer caching, the in-network
  hostname/env-var contract — is a real decision of its own and belongs
  with Q3's deploy work or its own session, not folded into this one as a
  side effect of adding probes. Recorded as an open question in
  `services/core-service/PLAN.md`.
- Kafka consumer death (a genuinely wedged poll loop that still returns
  successfully, or a broker outage the loop can't distinguish from idle, per
  the verified limitation above) remains invisible to any automated system
  — a human has to read the `riskSnapshotConsumer` detail to notice. This is
  named, tracked Q2 work, not a silent gap.
- Any future addition to `management.endpoint.health.group.readiness.include`
  in `application.yml` that reintroduces Kafka is a readiness-gating
  decision this ADR explicitly rejected;
  `RiskSnapshotConsumerReadinessExclusionTest` fails if that happens by
  accident.

## Alternatives considered
**Gate readiness on Kafka consumer health too.** Rejected: turns a
recoverable, already-tolerated staleness window (rebalance, replay, broker
blip) into a full outage of the REST read path, which never needed Kafka to
serve a read in the first place.

**One combined `/actuator/health` check for both liveness and readiness.**
Rejected: collapses the restart-storm-vs-remove-from-load-balancer
distinction that is the entire point of this ADR; an orchestrator needs the
two questions asked separately.

**Bake a staleness threshold (e.g. `lastPollAgeMillis > 60000` ⇒ DOWN) into
the Kafka detail.** Rejected: a threshold there is a readiness gate in
different clothing — the exact pattern under "Kafka as a detail, not a
gate" above — and, per the verified limitation, would not even reliably
detect the failure mode (broker outage) it would be aimed at.

**`server.servlet.context-path` to relocate actuator.** Already rejected by
ADR-0021 for reasons that apply unchanged here; not revisited.
