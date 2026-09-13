package com.meridian.coreservice.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.meridian.contracts.InstrumentType;
import com.meridian.contracts.OptionType;
import com.meridian.contracts.ReferenceInstrument;
import com.meridian.coreservice.audit.AuditLogRepository;
import com.meridian.coreservice.kafka.ReferenceInstrumentProducer;
import com.meridian.coreservice.web.dto.InstrumentDto;
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Savepoint;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Instrument creation: persists to {@code instruments} (the system of record, ADR-0019), appends an
 * {@code instrument_created} audit entry, and publishes to {@code reference.instruments} (ADR-0025)
 * -- same one-transaction, publish-last structure as {@link
 * PortfolioMutationService#createPortfolio}.
 *
 * <p>This replaces an earlier, never-called draft of {@code createInstrument} that persisted via
 * plain JPA {@code save()}: on an existing primary key, JPA {@code save} merges (an UPDATE), which
 * would have silently overwritten a stored instrument and republished the mutated version to {@code
 * reference.instruments} as fact -- see ADR-0025. This version follows {@code createPortfolio}'s
 * insert-first-with-{@code SAVEPOINT} technique instead, so a duplicate {@code instrument_id} fails
 * at the insert and is resolved to an explicit {@code 200}/{@code 409}, never a silent overwrite.
 */
@Service
public class InstrumentService {

  private static final String UNIQUE_VIOLATION_SQLSTATE = "23505";

  private final JdbcTemplate jdbcTemplate;
  private final ReferenceInstrumentProducer referenceInstrumentProducer;
  private final AuditLogRepository auditLogRepository;
  // Local, default-configured mapper for the audit payload only -- same reasoning as
  // PortfolioMutationService's auditObjectMapper: the payload's keys are already hand-written
  // snake_case and its BigDecimal fields are already toPlainString()'d.
  private final ObjectMapper auditObjectMapper = new ObjectMapper();

  public InstrumentService(
      JdbcTemplate jdbcTemplate,
      ReferenceInstrumentProducer referenceInstrumentProducer,
      AuditLogRepository auditLogRepository) {
    this.jdbcTemplate = jdbcTemplate;
    this.referenceInstrumentProducer = referenceInstrumentProducer;
    this.auditLogRepository = auditLogRepository;
  }

  /**
   * ADR-0025: creates an instrument. Like {@code createPortfolio} (ADR-0024, cited by ADR-0025),
   * there is no client-supplied idempotency key -- {@code instrument_id} is itself the request's
   * identity, and the resource is fully specified by its own fields, so a retry is detected by
   * comparing the persisted row, not a raw-byte fingerprint.
   *
   * <p>Order within this one {@code @Transactional} method is load-bearing, identical to {@code
   * createPortfolio}: insert first (a duplicate {@code instrument_id} fails here via the {@code
   * PRIMARY KEY} constraint), audit entry second, {@code reference.instruments} publish last, so a
   * publish failure rolls back the whole transaction.
   *
   * <p>{@code instrumentType}/{@code optionType} arrive already parsed into the generated Avro
   * enums -- {@link com.meridian.coreservice.web.InstrumentController} is where an unparseable
   * value and every conditional-field rule is rejected, per ADR-0025 (the Avro enum is the contract
   * of record, ADR-0002; no CHECK constraint duplicates it here).
   */
  @Transactional
  public InstrumentCreationOutcome createInstrument(
      String instrumentId,
      String underlyingId,
      InstrumentType instrumentType,
      OptionType optionType,
      BigDecimal strike,
      Instant expiry,
      String currency,
      BigDecimal contractSize) {
    // Truncated to microseconds at capture, same reasoning as ADR-0024's editorial amendment:
    // Postgres and the Avro decimal/enum encodings agree exactly on a value already quantized to
    // microseconds, so this instant is stable across the insert-now/read-back-later comparison a
    // duplicate request drives below.
    Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);

    boolean inserted =
        tryInsertInstrument(
            instrumentId,
            underlyingId,
            instrumentType,
            optionType,
            strike,
            expiry,
            currency,
            contractSize);
    if (!inserted) {
      InstrumentRow existing =
          findInstrumentRow(instrumentId)
              .orElseThrow(
                  () ->
                      new IllegalStateException(
                          "instrument insert lost race but no row found for instrument_id="
                              + instrumentId));
      boolean identical =
          existing.underlyingId().equals(underlyingId)
              && existing.instrumentType().equals(instrumentType)
              && Objects.equals(existing.optionType(), optionType)
              && bigDecimalEquals(existing.strike(), strike)
              && Objects.equals(existing.expiry(), expiry)
              && existing.currency().equals(currency)
              && bigDecimalEquals(existing.contractSize(), contractSize);
      if (!identical) {
        return new InstrumentCreationOutcome.Conflict();
      }
      return new InstrumentCreationOutcome.Existing(toDto(instrumentId, existing));
    }

    recordInstrumentCreatedAuditEntry(
        instrumentId,
        underlyingId,
        instrumentType,
        optionType,
        strike,
        expiry,
        currency,
        contractSize,
        now);

    ReferenceInstrument wire =
        new ReferenceInstrument(
            instrumentId,
            underlyingId,
            instrumentType,
            optionType,
            strike,
            expiry,
            currency,
            contractSize);
    referenceInstrumentProducer.publish(wire);

    return new InstrumentCreationOutcome.Created(
        new InstrumentDto(
            instrumentId,
            underlyingId,
            instrumentType,
            optionType,
            strike,
            expiry,
            currency,
            contractSize));
  }

  private static InstrumentDto toDto(String instrumentId, InstrumentRow row) {
    return new InstrumentDto(
        instrumentId,
        row.underlyingId(),
        row.instrumentType(),
        row.optionType(),
        row.strike(),
        row.expiry(),
        row.currency(),
        row.contractSize());
  }

  /**
   * {@code BigDecimal#equals} is scale-sensitive ("100" != "100.00"); duplicate detection must
   * compare numeric value only, matching how the same comparison is asserted on elsewhere in this
   * codebase (e.g. {@code isEqualByComparingTo} in the trade-booking tests).
   */
  private static boolean bigDecimalEquals(BigDecimal a, BigDecimal b) {
    if (a == null || b == null) {
      return a == b;
    }
    return a.compareTo(b) == 0;
  }

  /**
   * Attempts to insert the full instrument row. Returns {@code true} if this call created the row,
   * {@code false} if a row already existed for {@code instrumentId} -- same {@code
   * SAVEPOINT}-around-the-insert mechanism as {@code createPortfolio}/{@link
   * com.meridian.coreservice.idempotency.IdempotencyKeyRepository#tryClaim}, for the identical
   * reason: a failed {@code INSERT} aborts the rest of the enclosing Postgres transaction unless
   * rolled back to a savepoint taken immediately before it, and the caller needs the transaction
   * usable afterward to read the existing row.
   */
  private boolean tryInsertInstrument(
      String instrumentId,
      String underlyingId,
      InstrumentType instrumentType,
      OptionType optionType,
      BigDecimal strike,
      Instant expiry,
      String currency,
      BigDecimal contractSize) {
    return jdbcTemplate.execute(
        (ConnectionCallback<Boolean>)
            con -> {
              Savepoint savepoint = con.setSavepoint();
              try (PreparedStatement ps =
                  con.prepareStatement(
                      "INSERT INTO instruments (instrument_id, underlying_id, instrument_type,"
                          + " option_type, strike, expiry, currency, contract_size) VALUES (?, ?,"
                          + " ?, ?, ?, ?, ?, ?)")) {
                ps.setString(1, instrumentId);
                ps.setString(2, underlyingId);
                ps.setString(3, instrumentType.name());
                if (optionType == null) {
                  ps.setNull(4, Types.VARCHAR);
                } else {
                  ps.setString(4, optionType.name());
                }
                if (strike == null) {
                  ps.setNull(5, Types.NUMERIC);
                } else {
                  ps.setBigDecimal(5, strike);
                }
                if (expiry == null) {
                  ps.setNull(6, Types.TIMESTAMP_WITH_TIMEZONE);
                } else {
                  ps.setTimestamp(6, Timestamp.from(expiry));
                }
                ps.setString(7, currency);
                ps.setBigDecimal(8, contractSize);
                ps.executeUpdate();
                return true;
              } catch (SQLException e) {
                if (UNIQUE_VIOLATION_SQLSTATE.equals(e.getSQLState())) {
                  con.rollback(savepoint);
                  return false;
                }
                throw e;
              }
            });
  }

  private Optional<InstrumentRow> findInstrumentRow(String instrumentId) {
    List<InstrumentRow> rows =
        jdbcTemplate.query(
            "SELECT underlying_id, instrument_type, option_type, strike, expiry, currency,"
                + " contract_size FROM instruments WHERE instrument_id = ?",
            (rs, rowNum) -> {
              String optionTypeColumn = rs.getString("option_type");
              Timestamp expiryColumn = rs.getTimestamp("expiry");
              return new InstrumentRow(
                  rs.getString("underlying_id"),
                  InstrumentType.valueOf(rs.getString("instrument_type")),
                  optionTypeColumn == null ? null : OptionType.valueOf(optionTypeColumn),
                  rs.getBigDecimal("strike"),
                  expiryColumn == null ? null : expiryColumn.toInstant(),
                  rs.getString("currency"),
                  rs.getBigDecimal("contract_size"));
            },
            instrumentId);
    return rows.stream().findFirst();
  }

  private record InstrumentRow(
      String underlyingId,
      InstrumentType instrumentType,
      OptionType optionType,
      BigDecimal strike,
      Instant expiry,
      String currency,
      BigDecimal contractSize) {}

  private void recordInstrumentCreatedAuditEntry(
      String instrumentId,
      String underlyingId,
      InstrumentType instrumentType,
      OptionType optionType,
      BigDecimal strike,
      Instant expiry,
      String currency,
      BigDecimal contractSize,
      Instant eventTime) {
    // LinkedHashMap for deterministic field order -- the whole created resource is the payload
    // (CanonicalForm hashes entry_id + entry_type + payload only, per ADR-0024/ADR-0025), not a
    // summary of it.
    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("instrument_id", instrumentId);
    payload.put("underlying_id", underlyingId);
    payload.put("instrument_type", instrumentType.name());
    payload.put("option_type", optionType == null ? null : optionType.name());
    payload.put("strike", strike == null ? null : strike.toPlainString());
    payload.put("expiry", expiry == null ? null : expiry.toString());
    payload.put("currency", currency);
    payload.put("contract_size", contractSize.toPlainString());

    String payloadJson;
    try {
      payloadJson = auditObjectMapper.writeValueAsString(payload);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("failed to serialize instrument_created audit payload", e);
    }

    // ADR-0025: portfolio_id is null -- an instrument is not scoped to any one portfolio, so this
    // entry is reachable through no GET /portfolios/{id}/audit query, by design (see ADR-0025's
    // "Known consequence").
    auditLogRepository.append(
        UUID.randomUUID().toString(), "instrument_created", payloadJson, eventTime);
  }
}
