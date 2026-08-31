package com.meridian.coreservice.persistence.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** docs/domain-model.md#portfolio. Static/slow-changing metadata; positions live elsewhere. */
@Entity
@Table(name = "portfolios")
public class PortfolioEntity {

  @Id
  @Column(name = "portfolio_id")
  private String portfolioId;

  @Column(name = "name", nullable = false)
  private String name;

  @Column(name = "base_currency", nullable = false)
  private String baseCurrency;

  @Column(name = "owner", nullable = false)
  private String owner;

  protected PortfolioEntity() {}

  public PortfolioEntity(String portfolioId, String name, String baseCurrency, String owner) {
    this.portfolioId = portfolioId;
    this.name = name;
    this.baseCurrency = baseCurrency;
    this.owner = owner;
  }

  public String getPortfolioId() {
    return portfolioId;
  }

  public String getName() {
    return name;
  }

  public String getBaseCurrency() {
    return baseCurrency;
  }

  public String getOwner() {
    return owner;
  }
}
