package com.meridian.coreservice.web;

import com.meridian.coreservice.persistence.domain.PortfolioEntity;
import com.meridian.coreservice.persistence.domain.PositionEntity;
import com.meridian.coreservice.persistence.repository.PortfolioJpaRepository;
import com.meridian.coreservice.persistence.repository.PositionJpaRepository;
import com.meridian.coreservice.web.dto.PortfolioDto;
import com.meridian.coreservice.web.dto.PositionDto;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/** {@code GET /portfolios/{id}} and {@code GET /portfolios/{id}/positions}. */
@RestController
public class PortfolioController {

  private final PortfolioJpaRepository portfolioRepository;
  private final PositionJpaRepository positionRepository;

  public PortfolioController(
      PortfolioJpaRepository portfolioRepository, PositionJpaRepository positionRepository) {
    this.portfolioRepository = portfolioRepository;
    this.positionRepository = positionRepository;
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
