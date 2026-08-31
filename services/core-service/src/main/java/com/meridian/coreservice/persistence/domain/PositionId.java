package com.meridian.coreservice.persistence.domain;

import java.io.Serializable;
import java.util.Objects;

/** Composite primary key for {@link PositionEntity}: (portfolio_id, instrument_id). */
public class PositionId implements Serializable {

  private String portfolioId;
  private String instrumentId;

  protected PositionId() {}

  public PositionId(String portfolioId, String instrumentId) {
    this.portfolioId = portfolioId;
    this.instrumentId = instrumentId;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) return true;
    if (!(o instanceof PositionId that)) return false;
    return Objects.equals(portfolioId, that.portfolioId)
        && Objects.equals(instrumentId, that.instrumentId);
  }

  @Override
  public int hashCode() {
    return Objects.hash(portfolioId, instrumentId);
  }
}
