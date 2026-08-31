package com.meridian.coreservice.kafka;

import com.meridian.contracts.RiskSnapshot;
import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;
import com.meridian.coreservice.persistence.repository.RiskSnapshotRepository;
import org.springframework.stereotype.Component;

/**
 * Production {@link RiskSnapshotWriter}: converts the wire type and upserts via 05a's repository.
 */
@Component
public class RiskSnapshotRepositoryWriter implements RiskSnapshotWriter {

  private final RiskSnapshotRepository repository;

  public RiskSnapshotRepositoryWriter(RiskSnapshotRepository repository) {
    this.repository = repository;
  }

  @Override
  public void write(RiskSnapshot snapshot) {
    repository.upsert(
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
            snapshot.getIngestTime()));
  }
}
