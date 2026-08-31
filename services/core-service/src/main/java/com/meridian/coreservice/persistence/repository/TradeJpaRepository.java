package com.meridian.coreservice.persistence.repository;

import com.meridian.coreservice.persistence.domain.TradeEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TradeJpaRepository extends JpaRepository<TradeEntity, String> {}
