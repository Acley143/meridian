package com.meridian.coreservice.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.meridian.coreservice.service.PortfolioMutationService;
import com.meridian.coreservice.service.TradeBookingOutcome;
import com.meridian.coreservice.web.dto.TradeRequestDto;
import java.io.IOException;
import java.time.Instant;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * {@code POST /api/v1/trades} -- the first real caller of {@link PortfolioMutationService}.
 *
 * <p>ADR-0023: {@code Idempotency-Key} is required. The request body is read as raw bytes (never
 * re-parsed then re-serialized) so {@link
 * com.meridian.coreservice.idempotency.IdempotencyFingerprint} hashes exactly what the client sent
 * -- deserialization into {@link TradeRequestDto} happens afterward, from those same bytes, purely
 * to extract the fields {@link PortfolioMutationService} needs.
 */
@RestController
@RequestMapping("/api/v1")
public class TradeController {

  private static final String IDEMPOTENCY_ENDPOINT = "POST /api/v1/trades";

  private final PortfolioMutationService portfolioMutationService;
  private final ObjectMapper objectMapper;

  public TradeController(
      PortfolioMutationService portfolioMutationService, ObjectMapper objectMapper) {
    this.portfolioMutationService = portfolioMutationService;
    this.objectMapper = objectMapper;
  }

  @PostMapping("/trades")
  public ResponseEntity<Object> bookTrade(
      @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
      @RequestBody byte[] rawBody) {
    if (idempotencyKey == null || idempotencyKey.isBlank()) {
      throw new IllegalArgumentException("Idempotency-Key header is required");
    }

    TradeRequestDto request;
    try {
      request = objectMapper.readValue(rawBody, TradeRequestDto.class);
    } catch (IOException e) {
      throw new IllegalArgumentException("malformed trade request body", e);
    }

    Instant ingestTime = Instant.now();

    TradeBookingOutcome outcome =
        portfolioMutationService.applyTradeIdempotent(
            idempotencyKey,
            IDEMPOTENCY_ENDPOINT,
            rawBody,
            request.portfolioId(),
            request.instrumentId(),
            request.quantity(),
            request.price(),
            request.eventTime(),
            ingestTime);

    if (outcome instanceof TradeBookingOutcome.Created created) {
      return ResponseEntity.status(HttpStatus.CREATED).body(created.trade());
    }
    if (outcome instanceof TradeBookingOutcome.Replayed replayed) {
      return ResponseEntity.status(replayed.status())
          .contentType(MediaType.APPLICATION_JSON)
          .body(replayed.body());
    }
    return ResponseEntity.status(HttpStatus.CONFLICT)
        .body("Idempotency-Key already used with a different request body");
  }
}
