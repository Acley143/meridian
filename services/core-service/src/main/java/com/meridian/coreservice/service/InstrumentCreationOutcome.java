package com.meridian.coreservice.service;

import com.meridian.coreservice.web.dto.InstrumentDto;

/**
 * Result of {@link InstrumentService#createInstrument}, per ADR-0025. Same shape as {@link
 * PortfolioCreationOutcome} for the same reason: duplicate detection compares the persisted row's
 * fields, not a raw request-byte fingerprint -- ADR-0025 cites ADR-0024 rather than re-deriving
 * why.
 */
public sealed interface InstrumentCreationOutcome {

  /** No existing row for this {@code instrument_id}: the instrument was created fresh. */
  record Created(InstrumentDto instrument) implements InstrumentCreationOutcome {}

  /** A row already exists for this {@code instrument_id} and every field matches the request. */
  record Existing(InstrumentDto instrument) implements InstrumentCreationOutcome {}

  /** A row already exists for this {@code instrument_id} but at least one field differs. */
  record Conflict() implements InstrumentCreationOutcome {}
}
