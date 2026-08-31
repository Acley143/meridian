package com.meridian.coreservice.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * The database half of the cross-language decimal test (contracts/tests/python's is the
 * Python<->Java half). "79228162514.26433759" has 19 significant digits -- more than a double's
 * ~15-17 -- and is verified (see this class's comment below) to actually lose precision if
 * round-tripped through double: {@code (double) 79228162514.26433759 == 79228162514.26434326...}. A
 * NUMERIC(38,8) column must not do that.
 */
class DecimalRoundTripTest extends AbstractPostgresIntegrationTest {

  @Autowired private JdbcTemplate jdbcTemplate;

  // Confirms the chosen value actually IS double-lossy, so this test would fail if NUMERIC(38,8)
  // silently behaved like a double -- otherwise this test would pass by accident on any type.
  @Test
  void chosenValueActuallyLosesPrecisionAsADouble() {
    BigDecimal exact = new BigDecimal("79228162514.26433759");
    double asDouble = exact.doubleValue();
    BigDecimal roundTrippedThroughDouble = new BigDecimal(asDouble);

    assertThat(roundTrippedThroughDouble).isNotEqualByComparingTo(exact);
  }

  @Test
  void numeric38_8ColumnPreservesAValueThatWouldLosePrecisionAsADouble() {
    jdbcTemplate.execute("CREATE TEMP TABLE decimal_round_trip_probe (value NUMERIC(38, 8))");

    BigDecimal exact = new BigDecimal("79228162514.26433759");
    jdbcTemplate.update("INSERT INTO decimal_round_trip_probe (value) VALUES (?)", exact);

    BigDecimal roundTripped =
        jdbcTemplate.queryForObject("SELECT value FROM decimal_round_trip_probe", BigDecimal.class);

    assertThat(roundTripped).isEqualByComparingTo(exact);
    assertThat(roundTripped).isEqualTo(exact);
  }

  @Test
  void negativeAndLargeMagnitudeValuesAlsoRoundTripExactly() {
    jdbcTemplate.execute("CREATE TEMP TABLE decimal_round_trip_probe_2 (value NUMERIC(38, 8))");

    BigDecimal negative = new BigDecimal("-999999999999999999999999999999.99999999");
    jdbcTemplate.update("INSERT INTO decimal_round_trip_probe_2 (value) VALUES (?)", negative);

    BigDecimal roundTripped =
        jdbcTemplate.queryForObject(
            "SELECT value FROM decimal_round_trip_probe_2", BigDecimal.class);

    assertThat(roundTripped).isEqualByComparingTo(negative);
  }
}
