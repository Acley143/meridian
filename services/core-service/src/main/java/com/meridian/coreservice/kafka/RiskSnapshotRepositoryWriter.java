package com.meridian.coreservice.kafka;

import com.meridian.contracts.RiskSnapshot;
import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;
import com.meridian.coreservice.persistence.repository.RiskSnapshotRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

/**
 * Production {@link RiskSnapshotWriter}: converts the wire type, upserts via 05a's repository, then
 * publishes {@link RiskSnapshotPersistedEvent} -- strictly after the DB write succeeds, never
 * before, so a live SSE subscriber (05d) never sees a snapshot that isn't yet replayable on
 * reconnect.
 */
@Component
public class RiskSnapshotRepositoryWriter implements RiskSnapshotWriter {

  private final RiskSnapshotRepository repository;
  private final ApplicationEventPublisher eventPublisher;

  public RiskSnapshotRepositoryWriter(
      RiskSnapshotRepository repository, ApplicationEventPublisher eventPublisher) {
    this.repository = repository;
    this.eventPublisher = eventPublisher;
  }

  @Override
  public void write(RiskSnapshot snapshot) {
    RiskSnapshotRecord record =
        new RiskSnapshotRecord(
            snapshot.getPortfolioId(),
            snapshot.getAsOf(),
            snapshot.getPricerVersion(),
            snapshot.getPrice(),
            snapshot.getCashDelta(),
            snapshot.getCashGamma(),
            snapshot.getCashVega(),
            snapshot.getCashTheta(),
            snapshot.getCashRho(),
            snapshot.getVar95(),
            snapshot.getScenarioId(),
            snapshot.getOldestInputEventTime(),
            snapshot.getIngestTime());
    repository.upsert(record);
    eventPublisher.publishEvent(new RiskSnapshotPersistedEvent(record));
  }
}
