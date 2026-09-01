package com.meridian.coreservice.web;

import com.meridian.coreservice.service.PortfolioMutationService;
import com.meridian.coreservice.web.dto.TradeDto;
import com.meridian.coreservice.web.dto.TradeRequestDto;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * {@code POST /api/v1/trades} -- the first real caller of 05c's {@link PortfolioMutationService}.
 */
@RestController
@RequestMapping("/api/v1")
public class TradeController {

  private final PortfolioMutationService portfolioMutationService;

  public TradeController(PortfolioMutationService portfolioMutationService) {
    this.portfolioMutationService = portfolioMutationService;
  }

  @PostMapping("/trades")
  public ResponseEntity<TradeDto> bookTrade(@RequestBody TradeRequestDto request) {
    String tradeId = UUID.randomUUID().toString();
    Instant ingestTime = Instant.now();

    portfolioMutationService.applyTrade(
        tradeId,
        request.portfolioId(),
        request.instrumentId(),
        request.quantity(),
        request.price(),
        request.eventTime(),
        ingestTime);

    TradeDto response =
        new TradeDto(
            tradeId,
            request.portfolioId(),
            request.instrumentId(),
            request.quantity(),
            request.price(),
            request.eventTime(),
            ingestTime);
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
  }
}
