package com.meridian.coreservice.web;

import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;
import com.meridian.coreservice.web.dto.RiskSnapshotDto;

final class RiskSnapshotDtoMapper {

  private RiskSnapshotDtoMapper() {}

  static RiskSnapshotDto toDto(RiskSnapshotRecord r) {
    return new RiskSnapshotDto(
        r.portfolioId(),
        r.asOf(),
        r.pricerVersion(),
        r.price(),
        r.cashDelta(),
        r.cashGamma(),
        r.cashVega(),
        r.cashTheta(),
        r.cashRho(),
        r.var95(),
        r.scenarioId(),
        r.ingestTime());
  }
}
