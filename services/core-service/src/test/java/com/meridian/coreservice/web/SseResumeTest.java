package com.meridian.coreservice.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.meridian.coreservice.kafka.RiskSnapshotPersistedEvent;
import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;
import com.meridian.coreservice.persistence.repository.RiskSnapshotRepository;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;

/** ADR-0012 resume semantics (Task 4.1-4.3), against a real embedded HTTP server. */
class SseResumeTest extends AbstractRestIntegrationTest {

  @Autowired private RiskSnapshotRepository riskSnapshotRepository;
  @Autowired private ApplicationEventPublisher eventPublisher;
  @Autowired private JdbcTemplate jdbcTemplate;

  private RiskSnapshotRecord snap(String portfolioId, Instant asOf) {
    return new RiskSnapshotRecord(
        portfolioId,
        asOf,
        "v1.0.0",
        new BigDecimal("100.00000000"),
        BigDecimal.ONE,
        BigDecimal.ONE,
        BigDecimal.ONE,
        BigDecimal.ONE,
        BigDecimal.ONE,
        0.05,
        "scenario-1",
        asOf,
        Instant.now());
  }

  private void produceLive(RiskSnapshotRecord record) {
    riskSnapshotRepository.upsert(record);
    eventPublisher.publishEvent(new RiskSnapshotPersistedEvent(record));
  }

  @Test
  void reconnectWithLastEventIdMidStreamReplaysExactlyTheMissedSnapshotsNoGapsNoDuplicates()
      throws Exception {
    String portfolioId = "PF-SSE-RESUME";
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES (?, 'SSE"
            + " Resume Test', 'USD', 'desk-1') ON CONFLICT DO NOTHING",
        portfolioId);

    Instant t1 = Instant.parse("2026-08-31T10:00:00Z");
    Instant t2 = Instant.parse("2026-08-31T10:01:00Z");
    Instant t3 = Instant.parse("2026-08-31T10:02:00Z");

    String streamUrl = baseUrl() + "/api/v1/portfolios/" + portfolioId + "/risk/stream";

    // First connection, no Last-Event-ID.
    String lastReceivedId;
    try (SseTestClient client = new SseTestClient(streamUrl, null)) {
      assertThat(client.statusCode(Duration.ofSeconds(10))).isEqualTo(200);

      produceLive(snap(portfolioId, t1));
      SseTestClient.SseEvent eventA = client.nextEvent(Duration.ofSeconds(10));
      assertThat(eventA).isNotNull();
      assertThat(eventA.id()).isEqualTo(portfolioId + ":" + SseEventId.asOfMicros(t1) + ":v1.0.0");
      lastReceivedId = eventA.id();
    } // client disconnects (try-with-resources close) -- emitter unregisters from the broadcaster

    // Produced while disconnected -- must NOT be lost.
    produceLive(snap(portfolioId, t2));
    produceLive(snap(portfolioId, t3));

    // Reconnect with the last id actually received.
    try (SseTestClient client = new SseTestClient(streamUrl, lastReceivedId)) {
      assertThat(client.statusCode(Duration.ofSeconds(10))).isEqualTo(200);

      java.util.List<SseTestClient.SseEvent> replayed =
          client.drainAvailable(2, Duration.ofSeconds(15));

      assertThat(replayed).hasSize(2);
      assertThat(replayed.get(0).id())
          .isEqualTo(portfolioId + ":" + SseEventId.asOfMicros(t2) + ":v1.0.0");
      assertThat(replayed.get(1).id())
          .isEqualTo(portfolioId + ":" + SseEventId.asOfMicros(t3) + ":v1.0.0");

      // No gaps: exactly t2 and t3 -- not t1 again (no duplicate), not fewer than 2 (no gap).
      java.util.Set<String> ids = new java.util.HashSet<>();
      for (SseTestClient.SseEvent e : replayed) {
        assertThat(ids.add(e.id())).as("no duplicate event id " + e.id()).isTrue();
      }

      // Live streaming continues after replay catches up.
      Instant t4 = Instant.parse("2026-08-31T10:03:00Z");
      produceLive(snap(portfolioId, t4));
      SseTestClient.SseEvent live = client.nextEvent(Duration.ofSeconds(10));
      assertThat(live).isNotNull();
      assertThat(live.id()).isEqualTo(portfolioId + ":" + SseEventId.asOfMicros(t4) + ":v1.0.0");
    }
  }

  @Test
  void lastEventIdOlderThanTheBoundProducesResyncNotAFlood() throws Exception {
    String portfolioId = "PF-SSE-RESYNC";
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES (?, 'SSE"
            + " Resync Test', 'USD', 'desk-1') ON CONFLICT DO NOTHING",
        portfolioId);

    // A handful of recent snapshots. The age bound is measured against the newest persisted
    // as_of for the portfolio (ADR-0012's editorial amendment), not against wall-clock now() --
    // so the gap that must exceed 15 minutes is (newest as_of) - (Last-Event-ID's as_of), not
    // now() - (Last-Event-ID's as_of). Keeping these snapshots close to now ensures that gap is
    // ~20 minutes (below), well past the bound.
    Instant base = Instant.now().minus(Duration.ofSeconds(30));
    for (int i = 0; i < 5; i++) {
      riskSnapshotRepository.upsert(snap(portfolioId, base.plusSeconds(i)));
    }

    Instant tooOld = Instant.now().minus(Duration.ofMinutes(20));
    String oldEventId = portfolioId + ":" + SseEventId.asOfMicros(tooOld) + ":v1.0.0";

    String streamUrl = baseUrl() + "/api/v1/portfolios/" + portfolioId + "/risk/stream";
    try (SseTestClient client = new SseTestClient(streamUrl, oldEventId)) {
      assertThat(client.statusCode(Duration.ofSeconds(10))).isEqualTo(200);

      SseTestClient.SseEvent event = client.nextEvent(Duration.ofSeconds(10));
      assertThat(event).isNotNull();
      assertThat(event.eventName()).isEqualTo("resync");

      // Not a flood: nothing else arrives immediately after the resync event.
      SseTestClient.SseEvent extra = client.nextEvent(Duration.ofSeconds(2));
      assertThat(extra).isNull();
    }
  }

  @Test
  void replayStillWorksWhenAllSnapshotsAreFarFromWallClockNow() throws Exception {
    // ADR-0011: as_of is scenario-derived event time, deliberately decoupled from wall clock. A
    // historical scenario replay can have every as_of hours or days in the past relative to
    // Instant.now() while the snapshots themselves are seconds apart in event time -- the case
    // this test exercises should heal transparently via replay, not resync (ADR-0012's editorial
    // amendment: the age bound is measured against the newest persisted as_of for the portfolio,
    // not against now()).
    String portfolioId = "PF-SSE-HISTORICAL";
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES (?, 'SSE"
            + " Historical Replay Test', 'USD', 'desk-1') ON CONFLICT DO NOTHING",
        portfolioId);

    Instant farPast = Instant.parse("2020-01-01T00:00:00Z");
    Instant t1 = farPast;
    Instant t2 = farPast.plusSeconds(60);
    Instant t3 = farPast.plusSeconds(120);

    String streamUrl = baseUrl() + "/api/v1/portfolios/" + portfolioId + "/risk/stream";

    String lastReceivedId;
    try (SseTestClient client = new SseTestClient(streamUrl, null)) {
      assertThat(client.statusCode(Duration.ofSeconds(10))).isEqualTo(200);

      produceLive(snap(portfolioId, t1));
      SseTestClient.SseEvent eventA = client.nextEvent(Duration.ofSeconds(10));
      assertThat(eventA).isNotNull();
      lastReceivedId = eventA.id();
    }

    produceLive(snap(portfolioId, t2));
    produceLive(snap(portfolioId, t3));

    try (SseTestClient client = new SseTestClient(streamUrl, lastReceivedId)) {
      assertThat(client.statusCode(Duration.ofSeconds(10))).isEqualTo(200);

      java.util.List<SseTestClient.SseEvent> replayed =
          client.drainAvailable(2, Duration.ofSeconds(15));

      assertThat(replayed).hasSize(2);
      assertThat(replayed.get(0).id())
          .isEqualTo(portfolioId + ":" + SseEventId.asOfMicros(t2) + ":v1.0.0");
      assertThat(replayed.get(1).id())
          .isEqualTo(portfolioId + ":" + SseEventId.asOfMicros(t3) + ":v1.0.0");
      assertThat(replayed.stream().anyMatch(e -> "resync".equals(e.eventName()))).isFalse();
    }
  }

  @Test
  void malformedLastEventIdIsRejectedCleanlyNot500() throws Exception {
    String portfolioId = "PF-SSE-MALFORMED";
    String streamUrl = baseUrl() + "/api/v1/portfolios/" + portfolioId + "/risk/stream";

    try (SseTestClient client = new SseTestClient(streamUrl, "not-a-valid-event-id")) {
      int status = client.statusCode(Duration.ofSeconds(10));
      assertThat(status).isEqualTo(400);
    }
  }
}
