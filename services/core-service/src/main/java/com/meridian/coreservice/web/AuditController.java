package com.meridian.coreservice.web;

import com.meridian.coreservice.audit.AuditLogRepository;
import com.meridian.coreservice.audit.AuditLogRepository.AuditEntryRow;
import com.meridian.coreservice.web.dto.AuditEntryDto;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * {@code GET /api/v1/portfolios/{id}/audit}. services/core-service/PLAN.md scoped this to a Q1 501
 * stub pending the Q2 audit-log deliverable -- but ADR-0008's hash chain landed in Session 05b,
 * ahead of that schedule, and trade booking now writes a real {@code trade_booked} entry (see
 * PortfolioMutationService). Serving a permanently-empty 501 behind working functionality would be
 * a worse outcome than implementing the real query, so this wires up for real rather than keeping
 * the stub -- see PLAN.md's updated session log for the record of this decision.
 */
@RestController
@RequestMapping("/api/v1")
public class AuditController {

  private final AuditLogRepository auditLogRepository;

  public AuditController(AuditLogRepository auditLogRepository) {
    this.auditLogRepository = auditLogRepository;
  }

  @GetMapping("/portfolios/{portfolioId}/audit")
  public List<AuditEntryDto> getAudit(
      @PathVariable String portfolioId,
      @RequestParam(required = false, defaultValue = "100") int limit) {
    return auditLogRepository.findByPortfolioId(portfolioId, limit).stream()
        .map(AuditController::toDto)
        .toList();
  }

  private static AuditEntryDto toDto(AuditEntryRow row) {
    return new AuditEntryDto(
        row.entryId(),
        row.entryType(),
        row.payload(),
        row.prevHash(),
        row.entryHash(),
        row.eventTime(),
        row.ingestTime());
  }
}
