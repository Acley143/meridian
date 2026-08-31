package com.meridian.coreservice.persistence.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;

/**
 * docs/domain-model.md#position. Derived state -- the latest-applied-trade view for one
 * (portfolio_id, instrument_id) pair, not a history; {@link TradeEntity} is the append-only history
 * this is folded from.
 */
@Entity
@Table(name = "positions")
@IdClass(PositionId.class)
public class PositionEntity {

  @Id
  @Column(name = "portfolio_id")
  private String portfolioId;

  @Id
  @Column(name = "instrument_id")
  private String instrumentId;

  @Column(name = "quantity", nullable = false, precision = 38, scale = 8)
  private BigDecimal quantity;

  @Column(name = "average_cost", nullable = false, precision = 38, scale = 8)
  private BigDecimal averageCost;

  @Column(name = "as_of_event_time", nullable = false)
  private Instant asOfEventTime;

  protected PositionEntity() {}

  public PositionEntity(
      String portfolioId,
      String instrumentId,
      BigDecimal quantity,
      BigDecimal averageCost,
      Instant asOfEventTime) {
    this.portfolioId = portfolioId;
    this.instrumentId = instrumentId;
    this.quantity = quantity;
    this.averageCost = averageCost;
    this.asOfEventTime = asOfEventTime;
  }

  public String getPortfolioId() {
    return portfolioId;
  }

  public String getInstrumentId() {
    return instrumentId;
  }

  public BigDecimal getQuantity() {
    return quantity;
  }

  public BigDecimal getAverageCost() {
    return averageCost;
  }

  public Instant getAsOfEventTime() {
    return asOfEventTime;
  }
}
