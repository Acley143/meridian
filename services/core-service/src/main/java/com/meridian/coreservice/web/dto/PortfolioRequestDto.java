package com.meridian.coreservice.web.dto;

/**
 * Body of {@code POST /portfolios} (ADR-0024).
 * contracts/openapi/service-api.yaml#/components/schemas/PortfolioRequest.
 */
public record PortfolioRequestDto(
    String portfolioId, String name, String baseCurrency, String owner) {}
