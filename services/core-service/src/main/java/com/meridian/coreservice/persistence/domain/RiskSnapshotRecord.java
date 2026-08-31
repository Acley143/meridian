package com.meridian.coreservice.persistence.domain;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * docs/domain-model.md#risksnapshot. Not a JPA entity -- persisted through {@link
 * com.meridian.coreservice.persistence.repository.RiskSnapshotRepository}'s explicit upsert SQL,
 * not save(), since the identity (ADR-0007: portfolio_id, as_of, pricer_version) is a natural key
 * enforced by a database UNIQUE constraint, and the upsert semantics on conflict are a deliberate
 * decision better expressed as one SQL statement than coaxed out of JPA's entity lifecycle.
 */
public record RiskSnapshotRecord(
    String portfolioId,
    Instant asOf,
    String pricerVersion,
    BigDecimal price,
    BigDecimal cashDelta,
    BigDecimal cashGamma,
    BigDecimal cashVega,
    BigDecimal cashTheta,
    BigDecimal cashRho,
    double var95,
    String scenarioId,
    Instant oldestInputEventTime,
    Instant ingestTime) {}
