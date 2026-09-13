package com.meridian.coreservice.web;

import com.meridian.contracts.InstrumentType;
import com.meridian.contracts.OptionType;
import com.meridian.coreservice.service.InstrumentCreationOutcome;
import com.meridian.coreservice.service.InstrumentService;
import com.meridian.coreservice.web.dto.InstrumentRequestDto;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.EnumSet;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** {@code POST /api/v1/instruments} (ADR-0025). */
@RestController
@RequestMapping("/api/v1")
public class InstrumentController {

  private static final Pattern CURRENCY_PATTERN = Pattern.compile("^[A-Z]{3}$");

  /**
   * The only two {@link InstrumentType} values that carry {@code option_type}/{@code strike}/
   * {@code expiry}. A positive set, not {@code instrumentType != EQUITY}: {@code
   * reference-instruments.avsc} could gain a fourth {@code InstrumentType} in the future that is
   * still not option-bearing (or is, ambiguously) -- the negative rule would silently start
   * demanding a strike for it. This set is the one place that decision gets made; whoever adds a
   * new {@code InstrumentType} must extend this set deliberately, not inherit an assumption.
   */
  private static final Set<InstrumentType> OPTION_BEARING_TYPES =
      EnumSet.of(InstrumentType.VANILLA_EUROPEAN_OPTION, InstrumentType.VANILLA_AMERICAN_OPTION);

  private final InstrumentService instrumentService;

  public InstrumentController(InstrumentService instrumentService) {
    this.instrumentService = instrumentService;
  }

  /**
   * ADR-0025: unlike {@code POST /trades}, there is no {@code Idempotency-Key} header -- {@code
   * instrument_id} is itself the client-supplied identity, and duplicate detection compares the
   * persisted row (see {@link InstrumentService#createInstrument}), not a raw-byte fingerprint.
   */
  @PostMapping("/instruments")
  public ResponseEntity<Object> createInstrument(@RequestBody InstrumentRequestDto request) {
    requireNonBlank(request.instrumentId(), "instrument_id");
    requireNonBlank(request.underlyingId(), "underlying_id");
    requireNonBlank(request.instrumentType(), "instrument_type");
    requireNonBlank(request.currency(), "currency");

    InstrumentType instrumentType = parseInstrumentType(request.instrumentType());
    OptionType optionType = parseOptionType(request.optionType());

    if (!CURRENCY_PATTERN.matcher(request.currency()).matches()) {
      throw new InvalidInstrumentRequestException(
          "currency must match ^[A-Z]{3}$: " + request.currency());
    }
    if (request.contractSize() == null) {
      throw new InvalidInstrumentRequestException("contract_size is required");
    }
    if (request.contractSize().signum() <= 0) {
      throw new InvalidInstrumentRequestException("contract_size must be strictly positive");
    }

    boolean isOptionBearing = OPTION_BEARING_TYPES.contains(instrumentType);
    validateConditionalFields(isOptionBearing, request, optionType);

    // Truncated to microseconds, same reasoning as ADR-0024's editorial amendment on event_time:
    // docs/domain-model.md#instrument documents expiry as microsecond precision, and duplicate
    // detection later compares this value against what Postgres reads back -- quantizing it here
    // means that comparison can never disagree over a sub-microsecond remainder neither side ever
    // asked to keep.
    Instant expiry = isOptionBearing ? request.expiry().truncatedTo(ChronoUnit.MICROS) : null;
    BigDecimal strike = isOptionBearing ? request.strike() : null;
    OptionType effectiveOptionType = isOptionBearing ? optionType : null;

    InstrumentCreationOutcome outcome =
        instrumentService.createInstrument(
            request.instrumentId(),
            request.underlyingId(),
            instrumentType,
            effectiveOptionType,
            strike,
            expiry,
            request.currency(),
            request.contractSize());

    if (outcome instanceof InstrumentCreationOutcome.Created created) {
      return ResponseEntity.status(HttpStatus.CREATED).body(created.instrument());
    }
    if (outcome instanceof InstrumentCreationOutcome.Existing existing) {
      return ResponseEntity.status(HttpStatus.OK).body(existing.instrument());
    }
    return ResponseEntity.status(HttpStatus.CONFLICT)
        .body("instrument_id already exists with at least one different field");
  }

  private static void validateConditionalFields(
      boolean isOptionBearing, InstrumentRequestDto request, OptionType optionType) {
    if (isOptionBearing) {
      if (optionType == null) {
        throw new InvalidInstrumentRequestException(
            "option_type is required when instrument_type is " + request.instrumentType());
      }
      if (request.strike() == null) {
        throw new InvalidInstrumentRequestException(
            "strike is required when instrument_type is " + request.instrumentType());
      }
      if (request.expiry() == null) {
        throw new InvalidInstrumentRequestException(
            "expiry is required when instrument_type is " + request.instrumentType());
      }
    } else {
      if (optionType != null) {
        throw new InvalidInstrumentRequestException(
            "option_type must be absent when instrument_type is " + request.instrumentType());
      }
      if (request.strike() != null) {
        throw new InvalidInstrumentRequestException(
            "strike must be absent when instrument_type is " + request.instrumentType());
      }
      if (request.expiry() != null) {
        throw new InvalidInstrumentRequestException(
            "expiry must be absent when instrument_type is " + request.instrumentType());
      }
    }
  }

  private static InstrumentType parseInstrumentType(String raw) {
    try {
      return InstrumentType.valueOf(raw);
    } catch (IllegalArgumentException e) {
      throw new InvalidInstrumentRequestException("unknown instrument_type: " + raw);
    }
  }

  private static OptionType parseOptionType(String raw) {
    if (raw == null) {
      return null;
    }
    try {
      return OptionType.valueOf(raw);
    } catch (IllegalArgumentException e) {
      throw new InvalidInstrumentRequestException("unknown option_type: " + raw);
    }
  }

  private static void requireNonBlank(String value, String field) {
    if (value == null || value.isBlank()) {
      throw new InvalidInstrumentRequestException(field + " is required");
    }
  }
}
