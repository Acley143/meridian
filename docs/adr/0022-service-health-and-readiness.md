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
assignment), a second `AtomicReference` (a heartbeat-age reading, below),
and an `AtomicLong` (a poll-loop iteration counter) from inside its own
poll loop, immediately after each `pollOnce()` returns; the indicator only
reads those.

**A field that reported "fine" during a real failure was caught and
replaced, not shipped.** The first version of this indicator treated a
poll-loop-iteration timestamp (`pollThreadAlive`, `lastPollLoopIterationAt`)
as the Kafka detail's headline signal. Hand-testing against a real broker
outage (stopping the `kafka` container in `docker-compose.yml` while
`core-service` ran locally, then repeating it as an automated fixture —
`KafkaOutageReadinessExclusionFixtureTest`) showed that `KafkaConsumer.poll()`
does not throw when the broker is unreachable — it logs `Connection to node
N could not be established` and returns an empty batch, which the poll loop
correctly treats as a successful iteration. The timestamp kept advancing
through a *total* broker outage. That is worse than an absent field: it is
this system's characteristic failure mode (an absent signal rendering as a
normal one — the same shape `oldest_input_event_time` exists to prevent on
the dashboard) reproduced inside the very health check meant to catch it,
and it is exactly the kind of thing an on-call engineer checks first during
an incident.

The fix ships in this same change, not as a follow-up, and went through two
rounds of catching itself:

1. `pollThreadAlive` stays (Java thread liveness is unambiguous), but the
   timestamp/age pair is replaced with a bare `pollLoopIterationCount` —
   nobody reads "how many times has this loop run" as a claim about a
   remote broker, so the field name itself carries the meaning and no
   in-payload explanation is needed. An earlier draft of this fix kept the
   timestamp fields
   and added a literal `pollLoopIterationCaveat` string to the health body
   explaining what they didn't mean — rejected on review: prose in a health
   payload can't be asserted on by a test and will drift from the field it
   describes the moment either one changes without the other. The
   explanation now lives only in this ADR, `RiskSnapshotConsumerRunner`'s
   class doc, and the README's health section — the field name itself
   carries the meaning in the payload.
2. The new field, `lastHeartbeatSecondsAgo`, is sourced directly from
   `KafkaConsumer`'s own `consumer-coordinator-metrics` group
   (`last-heartbeat-seconds-ago`, read from inside the poll loop via
   `RiskSnapshotConsumerService.lastHeartbeatSecondsAgo()` — same
   single-thread-access constraint as `currentAssignment()`), because the
   group heartbeat genuinely stops succeeding when the coordinator is
   unreachable. Confirmed by re-running the outage fixture with the
   requirement inverted (the field **must** grow during the outage), not
   trusted by inspection — but that same hand-verification run caught a
   *second* instance of the identical failure shape inside the fix itself:
   `kafka-clients` 3.7.0's own metric implementation returns the literal
   sentinel `-1.0` — not `NaN` — when no heartbeat has ever been sent
   (`Heartbeat.lastHeartbeatSend() == 0`, decompiled and confirmed). A real
   `/actuator/health` response showed `"lastHeartbeatSecondsAgo": -1.0` at
   consumer startup before this was caught, which is exactly the same
   "plausible number reads as healthy" bug this field exists to eliminate,
   one layer down. `RiskSnapshotConsumerService.extractHeartbeatSecondsAgo`
   now treats any negative value the same as `NaN`/`Infinite`/non-numeric —
   all surface as `null`, never a number — and
   `RiskSnapshotConsumerHeartbeatMetricParsingTest` pins this with a
   dedicated case for the `-1.0` sentinel, run without Docker.

`RiskSnapshotConsumerRunner` also checks once, on its first successful poll
loop iteration, that a metric named `last-heartbeat-seconds-ago` is actually
registered on the running Kafka client (`heartbeatMetricIsRegistered()`),
and logs an `ERROR` if it isn't — a future `kafka-clients` upgrade that
renames the metric would otherwise silently degrade `lastHeartbeatSecondsAgo`
to always-`null` with nothing failing loudly on its own.

None of these fields carry a baked-in status threshold (no
`lastHeartbeatSecondsAgo > N ⇒ DOWN`): a threshold there is a readiness gate
wearing a different hat, precisely what this ADR rejects — the raw value
and its age are reported, and a human (or a future alert) judges what's too
old.

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
- Kafka consumer death (a genuinely wedged poll loop, which does still stop
  advancing `pollLoopIterationCount`/`pollThreadAlive`, or a broker outage,
  which `lastHeartbeatSecondsAgo` now reflects) remains invisible to any
  *automated* system — nothing pages on it, a human has to read the
  `riskSnapshotConsumer` detail to notice. This is named, tracked Q2 work
  (alerting on these fields), not a silent gap; the fields themselves are no
  longer silently wrong.
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

**Bake a staleness threshold (e.g. `lastHeartbeatSecondsAgo > 60` ⇒ DOWN)
into the Kafka detail.** Rejected: a threshold there is a readiness gate in
different clothing — the exact pattern under "Kafka as a detail, not a
gate" above. (An earlier draft of this ADR proposed thresholding the
poll-loop-iteration timestamp instead; that field doesn't move during a
broker outage at all — see the finding above — so a threshold on it
wouldn't even have detected the failure it would have been aimed at, on top
of being the wrong kind of gate.)

**`server.servlet.context-path` to relocate actuator.** Already rejected by
ADR-0021 for reasons that apply unchanged here; not revisited.
