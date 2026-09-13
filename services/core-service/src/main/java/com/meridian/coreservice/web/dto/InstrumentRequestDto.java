package com.meridian.coreservice.web.dto;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Body of {@code POST /instruments} (ADR-0025).
 * contracts/openapi/service-api.yaml#/components/schemas/InstrumentRequest.
 *
 * <p>{@code instrumentType}/{@code optionType} are raw strings, not the generated Avro enums --
 * {@link com.meridian.coreservice.web.InstrumentController} parses them at the controller edge and
 * rejects an unparseable value there, rather than letting Jackson's own enum coercion fail with a
 * different exception shape than every other 400 case in this controller.
 */
public record InstrumentRequestDto(
    String instrumentId,
    String underlyingId,
    String instrumentType,
    String optionType,
    BigDecimal strike,
    Instant expiry,
    String currency,
    BigDecimal contractSize) {}
