package com.meridian.coreservice.persistence.repository;

import com.meridian.coreservice.persistence.domain.PositionEntity;
import com.meridian.coreservice.persistence.domain.PositionId;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PositionJpaRepository extends JpaRepository<PositionEntity, PositionId> {}
