package com.meridian.coreservice.web.dto;

import java.math.BigDecimal;
import java.time.Instant;

/** contracts/openapi/service-api.yaml#/components/schemas/Trade. */
public record TradeDto(
    String tradeId,
    String portfolioId,
    String instrumentId,
    BigDecimal quantity,
    BigDecimal price,
    Instant eventTime,
    Instant ingestTime) {}
