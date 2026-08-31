package com.meridian.coreservice.web.dto;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Body of {@code POST /trades}.
 * contracts/openapi/service-api.yaml#/components/schemas/TradeRequest.
 */
public record TradeRequestDto(
    String portfolioId,
    String instrumentId,
    BigDecimal quantity,
    BigDecimal price,
    Instant eventTime) {}
