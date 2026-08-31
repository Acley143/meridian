package com.meridian.coreservice.kafka;

import com.meridian.contracts.RiskSnapshot;

/**
 * The write side {@link RiskSnapshotConsumerService} depends on to persist a consumed snapshot. An
 * interface (not a direct dependency on {@code RiskSnapshotRepository}) so tests can substitute a
 * writer that fails for a specific poisoned message, to prove the consumer does not commit past a
 * failed write -- see {@code OffsetCommitTest}.
 */
public interface RiskSnapshotWriter {
  void write(RiskSnapshot snapshot);
}
