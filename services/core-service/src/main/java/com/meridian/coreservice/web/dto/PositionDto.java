package com.meridian.coreservice.web.dto;

import java.math.BigDecimal;
import java.time.Instant;

/** contracts/openapi/service-api.yaml#/components/schemas/Position. */
public record PositionDto(
    String portfolioId,
    String instrumentId,
    BigDecimal quantity,
    BigDecimal averageCost,
    Instant asOfEventTime) {}
