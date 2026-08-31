package com.meridian.coreservice.persistence.repository;

import com.meridian.coreservice.persistence.domain.PortfolioEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PortfolioJpaRepository extends JpaRepository<PortfolioEntity, String> {}
