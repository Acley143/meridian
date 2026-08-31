package com.meridian.coreservice.kafka;

import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;

/**
 * Published after a snapshot is durably upserted to {@code risk_snapshots}. {@code web}'s SSE
 * broadcaster listens for this rather than being called directly, keeping the Kafka-consumption
 * layer decoupled from the web layer -- a snapshot's persistence doesn't need to know anything
 * about SSE existing.
 */
public record RiskSnapshotPersistedEvent(RiskSnapshotRecord snapshot) {}
