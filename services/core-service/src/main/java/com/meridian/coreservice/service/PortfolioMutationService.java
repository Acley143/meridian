package com.meridian.coreservice.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.meridian.contracts.Position;
import com.meridian.coreservice.audit.AuditLogRepository;
import com.meridian.coreservice.idempotency.IdempotencyFingerprint;
import com.meridian.coreservice.idempotency.IdempotencyKeyRepository;
import com.meridian.coreservice.idempotency.IdempotencyKeyRow;
import com.meridian.coreservice.kafka.PortfolioStateProducer;
import com.meridian.coreservice.persistence.domain.PositionEntity;
import com.meridian.coreservice.persistence.domain.TradeEntity;
import com.meridian.coreservice.persistence.repository.PositionJpaRepository;
import com.meridian.coreservice.persistence.repository.TradeJpaRepository;
import com.meridian.coreservice.web.dto.PortfolioDto;
import com.meridian.coreservice.web.dto.TradeDto;
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Savepoint;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Trade booking, and the position/state mutation it drives. No REST endpoint calls into this yet
 * ({@code POST /trades} is Session 05d) -- this is the internal, directly-testable seam 05d's
 * controller will call into, kept self-contained per this session's brief.
 *
 * <p>Every mutation republishes the affected portfolio's FULL current position set to {@code
 * portfolio.state} (ADR-0003) -- never a delta, per docs/domain-model.md#portfoliostate. This is
 * also the first point in the system where the pricer's upstream is a real running service rather
 * than services/pricer/fixtures/*.yaml; that fixture path is untouched and stays the cheaper test
 * path for the pricer's own tests.
 */
@Service
public class PortfolioMutationService {

  private static final String UNIQUE_VIOLATION_SQLSTATE = "23505";

  private final PositionJpaRepository positionRepository;
  private final TradeJpaRepository tradeRepository;
  private final PortfolioStateProducer portfolioStateProducer;
  private final AuditLogRepository auditLogRepository;
  private final IdempotencyKeyRepository idempotencyKeyRepository;
  private final JdbcTemplate jdbcTemplate;
  // Local, default-configured mapper for the audit payload only -- its keys are already
  // hand-written snake_case and its BigDecimal fields are already toPlainString()'d, so it never
  // needs the snake_case/money-as-string customizations JacksonConfig applies to the HTTP-facing
  // bean below.
  private final ObjectMapper auditObjectMapper = new ObjectMapper();
  // The Spring-managed, JacksonConfig-customized mapper -- used to serialize the stored
  // idempotency response so a replay is byte-identical to what the original HTTP response body
  // would have been.
  private final ObjectMapper responseObjectMapper;

  public PortfolioMutationService(
      PositionJpaRepository positionRepository,
      TradeJpaRepository tradeRepository,
      PortfolioStateProducer portfolioStateProducer,
      AuditLogRepository auditLogRepository,
      IdempotencyKeyRepository idempotencyKeyRepository,
      JdbcTemplate jdbcTemplate,
      ObjectMapper responseObjectMapper) {
    this.positionRepository = positionRepository;
    this.tradeRepository = tradeRepository;
    this.portfolioStateProducer = portfolioStateProducer;
    this.auditLogRepository = auditLogRepository;
    this.idempotencyKeyRepository = idempotencyKeyRepository;
    this.jdbcTemplate = jdbcTemplate;
    this.responseObjectMapper = responseObjectMapper;
  }

  /**
   * ADR-0024: creates a portfolio. Unlike {@link #applyTradeIdempotent}, there is no
   * client-supplied idempotency key -- {@code portfolio_id} is itself the request's identity, and
   * the resource is fully specified by its own fields, so a retry is detected by comparing the
   * persisted row, not a raw-byte fingerprint (ADR-0024's Decision).
   *
   * <p>Order within this one {@code @Transactional} method is load-bearing: the portfolio row is
   * inserted first (a duplicate {@code portfolio_id} fails here, via the {@code PRIMARY KEY}
   * constraint, before the JVM-synchronized audit section is ever reached); the audit entry is
   * appended second; {@code portfolio.state} is published last, so a publish failure rolls back the
   * whole transaction (the same rule {@link #applyTrade} already follows) -- a committed portfolio
   * row with no corresponding {@code portfolio.state} message never happens.
   *
   * <p>Duplicate handling does not check-then-insert (that TOCTOU race is exactly what {@link
   * IdempotencyKeyRepository#tryClaim} avoids for {@code POST /trades}): {@link
   * #tryInsertPortfolio} attempts the insert first, using the identical {@code SAVEPOINT} technique
   * as {@link IdempotencyKeyRepository#tryClaim} so a failed insert (unique violation) doesn't
   * abort the rest of the transaction and leave the follow-up read unable to run. A losing insert
   * means a row already exists: {@code name}/{@code base_currency}/{@code owner} all matching the
   * request is a replay (200, the stored row); any of them differing is a conflict (409) -- neither
   * path appends to the audit log or publishes {@code portfolio.state}, since nothing new happened.
   */
  @Transactional
  public PortfolioCreationOutcome createPortfolio(
      String portfolioId, String name, String baseCurrency, String owner) {
    // Truncated to microseconds at the source: Postgres (rounds to the nearest microsecond) and
    // the Avro timestamp-micros conversion (truncates) disagree on sub-microsecond nanos, so an
    // untruncated Instant.now() can publish a different event_time than the audit entry stores.
    Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);

    boolean inserted = tryInsertPortfolio(portfolioId, name, baseCurrency, owner);
    if (!inserted) {
      PortfolioRow existing =
          findPortfolioRow(portfolioId)
              .orElseThrow(
                  () ->
                      new IllegalStateException(
                          "portfolio insert lost race but no row found for portfolio_id="
                              + portfolioId));
      boolean identical =
          existing.name().equals(name)
              && existing.baseCurrency().equals(baseCurrency)
              && existing.owner().equals(owner);
      if (!identical) {
        return new PortfolioCreationOutcome.Conflict();
      }
      return new PortfolioCreationOutcome.Existing(
          new PortfolioDto(
              portfolioId, existing.name(), existing.baseCurrency(), existing.owner()));
    }

    recordPortfolioCreatedAuditEntry(portfolioId, name, baseCurrency, owner, now);
    portfolioStateProducer.publish(portfolioId, baseCurrency, List.of(), now);

    return new PortfolioCreationOutcome.Created(
        new PortfolioDto(portfolioId, name, baseCurrency, owner));
  }

  /**
   * Attempts to insert {@code (portfolio_id, name, base_currency, owner)}. Returns {@code true} if
   * this call created the row, {@code false} if a row already existed for {@code portfolio_id} --
   * same {@code SAVEPOINT}-around-the-insert mechanism as {@link
   * IdempotencyKeyRepository#tryClaim}, for the identical reason: a failed {@code INSERT} aborts
   * the rest of the enclosing Postgres transaction unless rolled back to a savepoint taken
   * immediately before it, and the caller needs the transaction usable afterward to read the
   * existing row.
   */
  private boolean tryInsertPortfolio(
      String portfolioId, String name, String baseCurrency, String owner) {
    return jdbcTemplate.execute(
        (ConnectionCallback<Boolean>)
            con -> {
              Savepoint savepoint = con.setSavepoint();
              try (PreparedStatement ps =
                  con.prepareStatement(
                      "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES"
                          + " (?, ?, ?, ?)")) {
                ps.setString(1, portfolioId);
                ps.setString(2, name);
                ps.setString(3, baseCurrency);
                ps.setString(4, owner);
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

  private Optional<PortfolioRow> findPortfolioRow(String portfolioId) {
    List<PortfolioRow> rows =
        jdbcTemplate.query(
            "SELECT name, base_currency, owner FROM portfolios WHERE portfolio_id = ?",
            (rs, rowNum) ->
                new PortfolioRow(
                    rs.getString("name"), rs.getString("base_currency"), rs.getString("owner")),
            portfolioId);
    return rows.stream().findFirst();
  }

  private record PortfolioRow(String name, String baseCurrency, String owner) {}

  private void recordPortfolioCreatedAuditEntry(
      String portfolioId, String name, String baseCurrency, String owner, Instant eventTime) {
    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("portfolio_id", portfolioId);
    payload.put("name", name);
    payload.put("base_currency", baseCurrency);
    payload.put("owner", owner);

    String payloadJson;
    try {
      payloadJson = auditObjectMapper.writeValueAsString(payload);
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("failed to serialize portfolio_created audit payload", e);
    }

    auditLogRepository.append(
        UUID.randomUUID().toString(), "portfolio_created", payloadJson, eventTime, portfolioId);
  }

  /**
   * ADR-0023: the idempotent entry point for {@code POST /trades}. Claims {@code (endpoint,
   * idempotencyKey)} first -- before any business mutation, including the audit append -- via
   * {@link IdempotencyKeyRepository#tryClaim}, inside this same {@code @Transactional} boundary. A
   * concurrent request for the same key blocks on that claim's row lock until this transaction
   * commits or rolls back (Postgres row lock), so no two concurrent callers can both pass the claim
   * and both reach {@link AuditLogRepository#append}'s JVM-level {@code synchronized} section for
   * the same key -- lock order is always Postgres row lock, then JVM audit lock.
   *
   * <p>A losing claim means a row already exists for this key: same fingerprint replays the stored
   * response verbatim (never re-minting {@code trade_id}); a different fingerprint is rejected with
   * {@link TradeBookingOutcome.Conflict}, never replayed.
   */
  @Transactional
  public TradeBookingOutcome applyTradeIdempotent(
      String idempotencyKey,
      String endpoint,
      byte[] rawRequestBody,
      String portfolioId,
      String instrumentId,
      BigDecimal quantity,
      BigDecimal price,
      Instant eventTime,
      Instant ingestTime) {
    String fingerprint = IdempotencyFingerprint.sha256Hex(rawRequestBody);

    boolean claimed = idempotencyKeyRepository.tryClaim(endpoint, idempotencyKey, fingerprint);
    if (!claimed) {
      IdempotencyKeyRow existing =
          idempotencyKeyRepository
              .find(endpoint, idempotencyKey)
              .orElseThrow(
                  () ->
                      new IllegalStateException(
                          "idempotency claim lost but no row found for endpoint="
                              + endpoint
                              + " key="
                              + idempotencyKey));
      if (!existing.requestFingerprint().equals(fingerprint)) {
        return new TradeBookingOutcome.Conflict();
      }
      return new TradeBookingOutcome.Replayed(existing.responseStatus(), existing.responseBody());
    }

    String tradeId = UUID.randomUUID().toString();
    applyTrade(tradeId, portfolioId, instrumentId, quantity, price, eventTime, ingestTime);

    TradeDto trade =
        new TradeDto(tradeId, portfolioId, instrumentId, quantity, price, eventTime, ingestTime);
    String responseBody;
    try {
      responseBody = responseObjectMapper.writeValueAsString(trade);
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException(
          "failed to serialize trade response for idempotency store", e);
    }
    idempotencyKeyRepository.storeResponse(
        endpoint, idempotencyKey, HttpStatus.CREATED.value(), responseBody);

    return new TradeBookingOutcome.Created(trade);
  }

  /**
   * Books one trade: persists the immutable {@code Trade} row, folds it into the affected
   * position's running (quantity, average_cost) per standard weighted-average-cost accounting, and
   * republishes the portfolio's full state.
   *
   * <p>The Kafka publish is the last statement in this method, deliberately: if it throws, Spring
   * rolls back the whole transaction (the default rollback rule for an unchecked exception), so a
   * failed publish never leaves a committed DB mutation with no corresponding portfolio.state
   * message. This is not a full outbox pattern (a publish that fails after the broker has already
   * durably accepted it, with the ack lost in transit, would still roll back a DB write that
   * actually shouldn't have been rolled back) -- that's a known, accepted gap for this session's
   * scope, not a hidden one.
   */
  @Transactional
  public void applyTrade(
      String tradeId,
      String portfolioId,
      String instrumentId,
      BigDecimal quantity,
      BigDecimal price,
      Instant eventTime,
      Instant ingestTime) {
    tradeRepository.save(
        new TradeEntity(
            tradeId, portfolioId, instrumentId, quantity, price, eventTime, ingestTime));

    Optional<PositionEntity> existing =
        positionRepository.findById(
            new com.meridian.coreservice.persistence.domain.PositionId(portfolioId, instrumentId));

    PositionEntity updated =
        foldTradeIntoPosition(existing, portfolioId, instrumentId, quantity, price, eventTime);
    positionRepository.save(updated);

    recordTradeBookedAuditEntry(
        tradeId, portfolioId, instrumentId, quantity, price, eventTime, ingestTime);

    republishPortfolioState(portfolioId, eventTime);
  }

  private void recordTradeBookedAuditEntry(
      String tradeId,
      String portfolioId,
      String instrumentId,
      BigDecimal quantity,
      BigDecimal price,
      Instant eventTime,
      Instant ingestTime) {
    // LinkedHashMap for deterministic field order in the payload -- CanonicalForm.java hashes
    // (entry_id, entry_type, payload) as opaque strings, so payload content only needs to be
    // reproducible JSON, not itself canonicalized by the same length-prefixed scheme.
    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("trade_id", tradeId);
    payload.put("portfolio_id", portfolioId);
    payload.put("instrument_id", instrumentId);
    payload.put("quantity", quantity.toPlainString());
    payload.put("price", price.toPlainString());
    payload.put("event_time", eventTime.toString());
    payload.put("ingest_time", ingestTime.toString());

    String payloadJson;
    try {
      payloadJson = auditObjectMapper.writeValueAsString(payload);
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("failed to serialize trade_booked audit payload", e);
    }

    auditLogRepository.append(
        UUID.randomUUID().toString(), "trade_booked", payloadJson, eventTime, portfolioId);
  }

  private PositionEntity foldTradeIntoPosition(
      Optional<PositionEntity> existing,
      String portfolioId,
      String instrumentId,
      BigDecimal tradeQuantity,
      BigDecimal tradePrice,
      Instant eventTime) {
    if (existing.isEmpty()) {
      return new PositionEntity(portfolioId, instrumentId, tradeQuantity, tradePrice, eventTime);
    }

    PositionEntity current = existing.get();
    BigDecimal oldQuantity = current.getQuantity();
    BigDecimal newQuantity = oldQuantity.add(tradeQuantity);

    boolean sameDirectionOrOpening =
        oldQuantity.signum() == 0 || oldQuantity.signum() == tradeQuantity.signum();

    BigDecimal newAverageCost;
    if (newQuantity.signum() == 0) {
      // Fully closed -- no remaining quantity to carry a cost basis for. Keep the last known
      // average cost rather than dividing by zero; it's meaningless for a flat position but
      // harmless, and avoids an arbitrary-exception edge case here.
      newAverageCost = current.getAverageCost();
    } else if (sameDirectionOrOpening) {
      // Adding to (or opening) a position: volume-weighted average of the old and new cost.
      BigDecimal totalCost =
          oldQuantity.multiply(current.getAverageCost()).add(tradeQuantity.multiply(tradePrice));
      newAverageCost = totalCost.divide(newQuantity, 8, java.math.RoundingMode.HALF_EVEN);
    } else if (oldQuantity.signum() == newQuantity.signum()) {
      // Partial close, same direction as before: cost basis of the remaining quantity is
      // unaffected by a partial reduction.
      newAverageCost = current.getAverageCost();
    } else {
      // Flipped through zero to the opposite side: the excess is a brand-new position at the
      // trade price, carrying no history from the closed-out side.
      newAverageCost = tradePrice;
    }

    return new PositionEntity(portfolioId, instrumentId, newQuantity, newAverageCost, eventTime);
  }

  private void republishPortfolioState(String portfolioId, Instant eventTime) {
    // Read the positions first: the auto-flush of this query is where an unknown portfolio_id or
    // instrument_id surfaces as a DataIntegrityViolationException, which GlobalExceptionHandler
    // maps to 400. The currency lookup below must come after it so that path is unchanged.
    List<PositionEntity> positions = positionRepository.findByPortfolioId(portfolioId);

    // portfolio.state carries the portfolio's reporting currency (ADR-0028), read from the
    // portfolios row inside this transaction. A missing row is an error, never an empty default.
    String baseCurrency =
        findPortfolioRow(portfolioId)
            .orElseThrow(
                () ->
                    new IllegalStateException(
                        "no portfolios row for portfolio_id="
                            + portfolioId
                            + " while republishing portfolio.state"))
            .baseCurrency();

    List<Position> wirePositions =
        positions.stream()
            .map(
                p ->
                    new Position(
                        p.getPortfolioId(),
                        p.getInstrumentId(),
                        p.getQuantity(),
                        p.getAverageCost(),
                        p.getAsOfEventTime()))
            .toList();

    portfolioStateProducer.publish(portfolioId, baseCurrency, wirePositions, eventTime);
  }
}
