package com.meridian.coreservice.persistence.repository;

import com.meridian.coreservice.persistence.domain.InstrumentEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InstrumentJpaRepository extends JpaRepository<InstrumentEntity, String> {}
