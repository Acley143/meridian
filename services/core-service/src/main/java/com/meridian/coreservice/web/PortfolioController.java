package com.meridian.coreservice.web;

import com.meridian.coreservice.persistence.domain.PortfolioEntity;
import com.meridian.coreservice.persistence.domain.PositionEntity;
import com.meridian.coreservice.persistence.repository.PortfolioJpaRepository;
import com.meridian.coreservice.persistence.repository.PositionJpaRepository;
import com.meridian.coreservice.service.PortfolioCreationOutcome;
import com.meridian.coreservice.service.PortfolioMutationService;
import com.meridian.coreservice.web.dto.PortfolioDto;
import com.meridian.coreservice.web.dto.PortfolioRequestDto;
import com.meridian.coreservice.web.dto.PositionDto;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * {@code GET /api/v1/portfolios/{id}}, {@code GET /api/v1/portfolios/{id}/positions}, and {@code
 * POST /api/v1/portfolios} (ADR-0024).
 */
@RestController
@RequestMapping("/api/v1")
public class PortfolioController {

  private static final Pattern BASE_CURRENCY_PATTERN = Pattern.compile("^[A-Z]{3}$");

  private final PortfolioJpaRepository portfolioRepository;
  private final PositionJpaRepository positionRepository;
  private final PortfolioMutationService portfolioMutationService;

  public PortfolioController(
      PortfolioJpaRepository portfolioRepository,
      PositionJpaRepository positionRepository,
      PortfolioMutationService portfolioMutationService) {
    this.portfolioRepository = portfolioRepository;
    this.positionRepository = positionRepository;
    this.portfolioMutationService = portfolioMutationService;
  }

  @GetMapping("/portfolios/{portfolioId}")
  public ResponseEntity<PortfolioDto> getPortfolio(@PathVariable String portfolioId) {
    return portfolioRepository
        .findById(portfolioId)
        .map(PortfolioController::toDto)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
  }

  @GetMapping("/portfolios/{portfolioId}/positions")
  public List<PositionDto> listPositions(@PathVariable String portfolioId) {
    return positionRepository.findByPortfolioId(portfolioId).stream()
        .map(PortfolioController::toDto)
        .toList();
  }

  /**
   * ADR-0024: unlike {@code POST /trades}, there is no {@code Idempotency-Key} header -- {@code
   * portfolio_id} is itself the client-supplied identity, and duplicate detection compares the
   * persisted row (see {@link PortfolioMutationService#createPortfolio}), not a raw-byte
   * fingerprint.
   */
  @PostMapping("/portfolios")
  public ResponseEntity<Object> createPortfolio(@RequestBody PortfolioRequestDto request) {
    validate(request);

    PortfolioCreationOutcome outcome =
        portfolioMutationService.createPortfolio(
            request.portfolioId(), request.name(), request.baseCurrency(), request.owner());

    if (outcome instanceof PortfolioCreationOutcome.Created created) {
      return ResponseEntity.status(HttpStatus.CREATED).body(created.portfolio());
    }
    if (outcome instanceof PortfolioCreationOutcome.Existing existing) {
      return ResponseEntity.status(HttpStatus.OK).body(existing.portfolio());
    }
    return ResponseEntity.status(HttpStatus.CONFLICT)
        .body("portfolio_id already exists with a different name, base_currency, or owner");
  }

  private static void validate(PortfolioRequestDto request) {
    requireNonBlank(request.portfolioId(), "portfolio_id");
    requireNonBlank(request.name(), "name");
    requireNonBlank(request.baseCurrency(), "base_currency");
    requireNonBlank(request.owner(), "owner");
    if (!BASE_CURRENCY_PATTERN.matcher(request.baseCurrency()).matches()) {
      throw new InvalidPortfolioRequestException(
          "base_currency must match ^[A-Z]{3}$: " + request.baseCurrency());
    }
  }

  private static void requireNonBlank(String value, String field) {
    if (value == null || value.isBlank()) {
      throw new InvalidPortfolioRequestException(field + " is required");
    }
  }

  private static PortfolioDto toDto(PortfolioEntity e) {
    return new PortfolioDto(e.getPortfolioId(), e.getName(), e.getBaseCurrency(), e.getOwner());
  }

  private static PositionDto toDto(PositionEntity e) {
    return new PositionDto(
        e.getPortfolioId(),
        e.getInstrumentId(),
        e.getQuantity(),
        e.getAverageCost(),
        e.getAsOfEventTime());
  }
}
