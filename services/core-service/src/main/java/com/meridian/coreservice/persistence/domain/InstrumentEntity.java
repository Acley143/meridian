package com.meridian.coreservice.persistence.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;

/**
 * core-service's system-of-record row for docs/domain-model.md#instrument. core-service is the sole
 * producer of the reference.instruments topic (ADR-0019); this is what it publishes from. A changed
 * strike/expiry is a new instrument, never an update to an existing row -- rows here are inserted,
 * not mutated, per the domain model.
 */
@Entity
@Table(name = "instruments")
public class InstrumentEntity {

  @Id
  @Column(name = "instrument_id")
  private String instrumentId;

  @Column(name = "underlying_id", nullable = false)
  private String underlyingId;

  @Column(name = "instrument_type", nullable = false)
  private String instrumentType;

  @Column(name = "option_type")
  private String optionType;

  @Column(name = "strike", precision = 38, scale = 8)
  private BigDecimal strike;

  @Column(name = "expiry")
  private Instant expiry;

  @Column(name = "currency", nullable = false)
  private String currency;

  @Column(name = "contract_size", nullable = false, precision = 38, scale = 8)
  private BigDecimal contractSize;

  protected InstrumentEntity() {}

  public InstrumentEntity(
      String instrumentId,
      String underlyingId,
      String instrumentType,
      String optionType,
      BigDecimal strike,
      Instant expiry,
      String currency,
      BigDecimal contractSize) {
    this.instrumentId = instrumentId;
    this.underlyingId = underlyingId;
    this.instrumentType = instrumentType;
    this.optionType = optionType;
    this.strike = strike;
    this.expiry = expiry;
    this.currency = currency;
    this.contractSize = contractSize;
  }

  public String getInstrumentId() {
    return instrumentId;
  }

  public String getUnderlyingId() {
    return underlyingId;
  }

  public String getInstrumentType() {
    return instrumentType;
  }

  public String getOptionType() {
    return optionType;
  }

  public BigDecimal getStrike() {
    return strike;
  }

  public Instant getExpiry() {
    return expiry;
  }

  public String getCurrency() {
    return currency;
  }

  public BigDecimal getContractSize() {
    return contractSize;
  }
}
