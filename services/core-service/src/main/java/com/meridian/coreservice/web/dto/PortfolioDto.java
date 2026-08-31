package com.meridian.coreservice.web.dto;

/** contracts/openapi/service-api.yaml#/components/schemas/Portfolio. */
public record PortfolioDto(String portfolioId, String name, String baseCurrency, String owner) {}
