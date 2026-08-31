package com.meridian.coreservice.service;

import com.meridian.contracts.InstrumentType;
import com.meridian.contracts.OptionType;
import com.meridian.contracts.ReferenceInstrument;
import com.meridian.coreservice.kafka.ReferenceInstrumentProducer;
import com.meridian.coreservice.persistence.domain.InstrumentEntity;
import com.meridian.coreservice.persistence.repository.InstrumentJpaRepository;
import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Instrument creation: persists to {@code instruments} (the system of record, ADR-0019) and
 * publishes to {@code reference.instruments}. No REST endpoint calls into this yet -- an internal
 * seam for a future session/05d to expose, same reasoning as {@link PortfolioMutationService}.
 */
@Service
public class InstrumentService {

  private final InstrumentJpaRepository instrumentRepository;
  private final ReferenceInstrumentProducer referenceInstrumentProducer;

  public InstrumentService(
      InstrumentJpaRepository instrumentRepository,
      ReferenceInstrumentProducer referenceInstrumentProducer) {
    this.instrumentRepository = instrumentRepository;
    this.referenceInstrumentProducer = referenceInstrumentProducer;
  }

  /**
   * See the class doc's publish-last-in-transaction reasoning, same as {@link
   * PortfolioMutationService}.
   */
  @Transactional
  public void createInstrument(
      String instrumentId,
      String underlyingId,
      String instrumentType,
      String optionType,
      BigDecimal strike,
      Instant expiry,
      String currency,
      BigDecimal contractSize) {
    instrumentRepository.save(
        new InstrumentEntity(
            instrumentId,
            underlyingId,
            instrumentType,
            optionType,
            strike,
            expiry,
            currency,
            contractSize));

    ReferenceInstrument wire =
        new ReferenceInstrument(
            instrumentId,
            underlyingId,
            InstrumentType.valueOf(instrumentType),
            optionType == null ? null : OptionType.valueOf(optionType),
            strike,
            expiry,
            currency,
            contractSize);
    referenceInstrumentProducer.publish(wire);
  }
}
