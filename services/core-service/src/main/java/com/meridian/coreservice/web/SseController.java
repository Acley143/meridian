package com.meridian.coreservice.web;

import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;
import com.meridian.coreservice.persistence.repository.RiskSnapshotRepository;
import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * {@code GET /portfolios/{id}/risk/stream}, resume semantics per ADR-0012.
 *
 * <p>Known limitation, accepted for this session's scope: a live snapshot written and published
 * (05c's {@link com.meridian.coreservice.kafka.RiskSnapshotPersistedEvent}) at the exact moment a
 * reconnecting client's replay query is running could theoretically arrive out of order relative to
 * the replay batch (the emitter is subscribed for live delivery before the replay query runs, so a
 * concurrent write is not lost, but its exact interleaving with the replay batch's sends is not
 * strictly ordered). Not exercised by this session's tests, which produce in distinct phases; a
 * fully ordered solution would need a per-subscriber buffered queue, out of scope here.
 */
@RestController
public class SseController {

  static final int MAX_REPLAY_SNAPSHOTS = 500;
  static final Duration MAX_REPLAY_AGE = Duration.ofMinutes(15);

  private final RiskSnapshotRepository riskSnapshotRepository;
  private final RiskSnapshotBroadcaster broadcaster;

  public SseController(
      RiskSnapshotRepository riskSnapshotRepository, RiskSnapshotBroadcaster broadcaster) {
    this.riskSnapshotRepository = riskSnapshotRepository;
    this.broadcaster = broadcaster;
  }

  @GetMapping(
      value = "/portfolios/{portfolioId}/risk/stream",
      produces = MediaType.TEXT_EVENT_STREAM_VALUE)
  public SseEmitter stream(
      @PathVariable String portfolioId,
      @RequestHeader(value = "Last-Event-ID", required = false) String lastEventId) {
    // Parse (and validate) BEFORE creating/subscribing an emitter: a malformed header must fail
    // cleanly with a 400 and no dangling emitter left registered anywhere (GlobalExceptionHandler
    // maps the IllegalArgumentException).
    SseEventId parsed = null;
    if (lastEventId != null) {
      parsed = SseEventId.parse(lastEventId);
      if (!parsed.portfolioId().equals(portfolioId)) {
        throw new IllegalArgumentException(
            "Last-Event-ID's portfolio_id ("
                + parsed.portfolioId()
                + ") does not match the"
                + " stream's portfolio_id ("
                + portfolioId
                + ")");
      }
    }

    SseEmitter emitter = new SseEmitter(0L);

    // Subscribe before replaying: a live snapshot published while the replay query below is
    // still running is delivered (not lost), at the cost of the ordering caveat in the class doc.
    broadcaster.subscribe(portfolioId, emitter);

    // Force the response headers out immediately, on every connection, before any replay or live
    // event: nothing else here writes to the emitter until a snapshot exists to send, so with no
    // Last-Event-ID (no replay) and a quiet portfolio, the response would otherwise sit unflushed
    // in the servlet container's buffer indefinitely -- the connection never actually opens from
    // the client's point of view (a browser's EventSource.onopen never fires; nothing distinguishes
    // "open, no data yet" from "never opened"). A comment frame is ignored by EventSource clients,
    // so this changes nothing observable except that the connection commits.
    try {
      emitter.send(SseEmitter.event().comment("connected"));
    } catch (IOException e) {
      emitter.completeWithError(e);
      return emitter;
    }

    if (parsed != null) {
      replayOrResync(emitter, portfolioId, parsed.asOf());
    }

    return emitter;
  }

  private void replayOrResync(SseEmitter emitter, String portfolioId, Instant afterAsOf) {
    long count = riskSnapshotRepository.countAfter(portfolioId, afterAsOf);
    // Age bound is measured against the newest persisted as_of for this portfolio, not
    // Instant.now() -- as_of is scenario-derived event time (ADR-0011), deliberately decoupled
    // from wall clock, so comparing it to now() resyncs every reconnect for any scenario whose
    // as_of isn't approximately current wall-clock time. See ADR-0012's editorial amendment. No
    // snapshots at all for this portfolio means nothing to be "too old" relative to.
    boolean tooOld =
        riskSnapshotRepository
            .findMaxAsOf(portfolioId)
            .map(newest -> Duration.between(afterAsOf, newest).compareTo(MAX_REPLAY_AGE) > 0)
            .orElse(false);

    try {
      if (count > MAX_REPLAY_SNAPSHOTS || tooOld) {
        emitter.send(SseEmitter.event().name("resync").data(""));
        return;
      }
      List<RiskSnapshotRecord> toReplay = riskSnapshotRepository.findAfter(portfolioId, afterAsOf);
      for (RiskSnapshotRecord snapshot : toReplay) {
        String eventId =
            new SseEventId(snapshot.portfolioId(), snapshot.asOf(), snapshot.pricerVersion())
                .format();
        emitter.send(SseEmitter.event().id(eventId).data(RiskSnapshotDtoMapper.toDto(snapshot)));
      }
    } catch (IOException e) {
      emitter.completeWithError(e);
    }
  }
}
