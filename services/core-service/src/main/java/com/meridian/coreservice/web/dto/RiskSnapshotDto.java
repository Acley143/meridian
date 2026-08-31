package com.meridian.coreservice.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.time.Instant;

/** contracts/openapi/service-api.yaml#/components/schemas/RiskSnapshot. */
public record RiskSnapshotDto(
    String portfolioId,
    Instant asOf,
    String pricerVersion,
    BigDecimal price,
    BigDecimal cashDelta,
    BigDecimal cashGamma,
    BigDecimal cashVega,
    BigDecimal cashTheta,
    BigDecimal cashRho,
    // Explicit @JsonProperty: the snake_case naming strategy has no case-transition to key off
    // between a word and a trailing digit ("var95" would stay "var95", not "var_95").
    @JsonProperty("var_95") double var95,
    String scenarioId,
    Instant ingestTime) {}
