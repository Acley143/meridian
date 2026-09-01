package com.meridian.coreservice.web;

import com.meridian.coreservice.persistence.repository.RiskSnapshotRepository;
import com.meridian.coreservice.web.dto.RiskSnapshotDto;
import java.time.Instant;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * {@code GET /api/v1/portfolios/{id}/risk} and {@code GET /api/v1/portfolios/{id}/risk/history}.
 */
@RestController
@RequestMapping("/api/v1")
public class RiskController {

  private final RiskSnapshotRepository riskSnapshotRepository;

  public RiskController(RiskSnapshotRepository riskSnapshotRepository) {
    this.riskSnapshotRepository = riskSnapshotRepository;
  }

  /**
   * "Latest, under the latest pricer_version" (spec wording): pricer_version strings aren't
   * necessarily lexicographically sortable in a meaningful way (e.g. v1.0.0 vs v1.10.0), so
   * "latest" is resolved by ingest_time -- the most recently produced row, which reflects whichever
   * pricer_version is currently active in practice, without depending on the version string's own
   * ordering.
   */
  @GetMapping("/portfolios/{portfolioId}/risk")
  public ResponseEntity<RiskSnapshotDto> getLatestRisk(@PathVariable String portfolioId) {
    return riskSnapshotRepository
        .findLatest(portfolioId)
        .map(RiskSnapshotDtoMapper::toDto)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
  }

  @GetMapping("/portfolios/{portfolioId}/risk/history")
  public List<RiskSnapshotDto> getRiskHistory(
      @PathVariable String portfolioId,
      @RequestParam Instant from,
      @RequestParam Instant to,
      @RequestParam(required = false, defaultValue = "500") int limit) {
    if (from.isAfter(to)) {
      throw new ResponseStatusException(
          org.springframework.http.HttpStatus.BAD_REQUEST, "from is after to");
    }
    if (limit < 1 || limit > 500) {
      throw new ResponseStatusException(
          org.springframework.http.HttpStatus.BAD_REQUEST, "limit must be in [1, 500]");
    }
    return riskSnapshotRepository.findHistory(portfolioId, from, to, limit).stream()
        .map(RiskSnapshotDtoMapper::toDto)
        .toList();
  }
}
