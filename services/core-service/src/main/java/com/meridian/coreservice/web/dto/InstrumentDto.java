package com.meridian.coreservice.web.dto;

import com.meridian.contracts.InstrumentType;
import com.meridian.contracts.OptionType;
import java.math.BigDecimal;
import java.time.Instant;

/** contracts/openapi/service-api.yaml#/components/schemas/Instrument. */
public record InstrumentDto(
    String instrumentId,
    String underlyingId,
    InstrumentType instrumentType,
    OptionType optionType,
    BigDecimal strike,
    Instant expiry,
    String currency,
    BigDecimal contractSize) {}
