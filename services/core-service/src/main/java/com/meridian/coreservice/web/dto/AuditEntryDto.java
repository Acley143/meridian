package com.meridian.coreservice.web.dto;

import java.time.Instant;

/** contracts/openapi/service-api.yaml#/components/schemas/AuditEntry. */
public record AuditEntryDto(
    String entryId,
    String entryType,
    String payload,
    String prevHash,
    String entryHash,
    Instant eventTime,
    Instant ingestTime) {}
