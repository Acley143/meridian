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
import com.meridian.coreservice.web.dto.TradeDto;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.HttpStatus;
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

  private final PositionJpaRepository positionRepository;
  private final TradeJpaRepository tradeRepository;
  private final PortfolioStateProducer portfolioStateProducer;
  private final AuditLogRepository auditLogRepository;
  private final IdempotencyKeyRepository idempotencyKeyRepository;
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
      ObjectMapper responseObjectMapper) {
    this.positionRepository = positionRepository;
    this.tradeRepository = tradeRepository;
    this.portfolioStateProducer = portfolioStateProducer;
    this.auditLogRepository = auditLogRepository;
    this.idempotencyKeyRepository = idempotencyKeyRepository;
    this.responseObjectMapper = responseObjectMapper;
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
    List<PositionEntity> positions = positionRepository.findByPortfolioId(portfolioId);

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

    portfolioStateProducer.publish(portfolioId, wirePositions, eventTime);
  }
}
