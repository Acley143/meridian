package com.meridian.coreservice.persistence.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;

/**
 * docs/domain-model.md#trade. Immutable, append-only source of truth -- never updated or deleted; a
 * correction is a new trade with an offsetting entry.
 */
@Entity
@Table(name = "trades")
public class TradeEntity {

  @Id
  @Column(name = "trade_id")
  private String tradeId;

  @Column(name = "portfolio_id", nullable = false)
  private String portfolioId;

  @Column(name = "instrument_id", nullable = false)
  private String instrumentId;

  @Column(name = "quantity", nullable = false, precision = 38, scale = 8)
  private BigDecimal quantity;

  @Column(name = "price", nullable = false, precision = 38, scale = 8)
  private BigDecimal price;

  @Column(name = "event_time", nullable = false)
  private Instant eventTime;

  @Column(name = "ingest_time", nullable = false)
  private Instant ingestTime;

  protected TradeEntity() {}

  public TradeEntity(
      String tradeId,
      String portfolioId,
      String instrumentId,
      BigDecimal quantity,
      BigDecimal price,
      Instant eventTime,
      Instant ingestTime) {
    this.tradeId = tradeId;
    this.portfolioId = portfolioId;
    this.instrumentId = instrumentId;
    this.quantity = quantity;
    this.price = price;
    this.eventTime = eventTime;
    this.ingestTime = ingestTime;
  }

  public String getTradeId() {
    return tradeId;
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

  public BigDecimal getPrice() {
    return price;
  }

  public Instant getEventTime() {
    return eventTime;
  }

  public Instant getIngestTime() {
    return ingestTime;
  }
}
