package com.meridian.contracts;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.apache.avro.io.BinaryDecoder;
import org.apache.avro.io.BinaryEncoder;
import org.apache.avro.io.DecoderFactory;
import org.apache.avro.io.EncoderFactory;
import org.apache.avro.specific.SpecificDatumReader;
import org.apache.avro.specific.SpecificDatumWriter;
import org.junit.jupiter.api.Test;

/**
 * Round-trip tests (Java side): serialize, deserialize, assert equality
 * across every field, for every generated record type. Companion to
 * contracts/tests/python/test_round_trip.py -- same principle, other
 * language. See test_cross_language_decimal.py for the test that actually
 * exercises both languages against the same bytes.
 */
class RoundTripTest {

  private static <T extends org.apache.avro.specific.SpecificRecordBase> T roundTrip(
      T record, Class<T> clazz) throws Exception {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    BinaryEncoder encoder = EncoderFactory.get().binaryEncoder(out, null);
    new SpecificDatumWriter<>(clazz).write(record, encoder);
    encoder.flush();

    BinaryDecoder decoder = DecoderFactory.get().binaryDecoder(out.toByteArray(), null);
    return new SpecificDatumReader<>(clazz).read(null, decoder);
  }

  @Test
  void tickRoundTrips() throws Exception {
    Tick tick =
        new Tick(
            "AAPL",
            new BigDecimal("189.32000000"),
            "USD",
            Instant.parse("2026-01-01T00:00:00.000001Z"),
            Instant.parse("2026-01-01T00:00:00.000501Z"),
            "scenario-1");

    Tick back = roundTrip(tick, Tick.class);

    assertEquals(tick.getInstrumentId(), back.getInstrumentId());
    assertEquals(tick.getPrice(), back.getPrice());
    assertEquals(tick.getCurrency(), back.getCurrency());
    assertEquals(tick.getEventTime(), back.getEventTime());
    assertEquals(tick.getIngestTime(), back.getIngestTime());
    assertEquals(tick.getScenarioId(), back.getScenarioId());
  }

  @Test
  void tickKeyRoundTrips() throws Exception {
    TickKey key = new TickKey("AAPL");
    TickKey back = roundTrip(key, TickKey.class);
    assertEquals(key.getInstrumentId(), back.getInstrumentId());
  }

  @Test
  void riskSnapshotRoundTrips() throws Exception {
    RiskSnapshot snap =
        new RiskSnapshot(
            "portfolio-1",
            Instant.parse("2026-01-01T00:00:00.123456Z"),
            "0.1.0",
            new BigDecimal("1234567.87654321"),
            new BigDecimal("63000.12345678"),
            new BigDecimal("1800.00000001"),
            new BigDecimal("37500.00000000"),
            new BigDecimal("-6400.00000000"),
            new BigDecimal("53200.00000000"),
            125000.0,
            "scenario-1",
            Instant.parse("2026-01-01T00:00:00.111111Z"),
            Instant.parse("2026-01-01T00:00:00.654321Z"));

    RiskSnapshot back = roundTrip(snap, RiskSnapshot.class);

    assertEquals(snap.getPortfolioId(), back.getPortfolioId());
    assertEquals(snap.getAsOf(), back.getAsOf());
    assertEquals(snap.getPricerVersion(), back.getPricerVersion());
    assertEquals(snap.getPrice(), back.getPrice());
    assertEquals(snap.getCashDelta(), back.getCashDelta());
    assertEquals(snap.getCashGamma(), back.getCashGamma());
    assertEquals(snap.getCashVega(), back.getCashVega());
    assertEquals(snap.getCashTheta(), back.getCashTheta());
    assertEquals(snap.getCashRho(), back.getCashRho());
    assertEquals(snap.getVar95(), back.getVar95());
    assertEquals(snap.getScenarioId(), back.getScenarioId());
    assertEquals(snap.getIngestTime(), back.getIngestTime());
  }

  @Test
  void riskSnapshotKeyRoundTrips() throws Exception {
    RiskSnapshotKey key = new RiskSnapshotKey("portfolio-1");
    RiskSnapshotKey back = roundTrip(key, RiskSnapshotKey.class);
    assertEquals(key.getPortfolioId(), back.getPortfolioId());
  }

  @Test
  void portfolioStateRoundTripsIncludingNestedPositions() throws Exception {
    Position position =
        new Position(
            "portfolio-1",
            "AAPL",
            new BigDecimal("100.00000000"),
            new BigDecimal("150.25000000"),
            Instant.parse("2026-01-01T00:00:00.000001Z"));

    PortfolioState state =
        new PortfolioState(
            "portfolio-1",
            List.of(position),
            Instant.parse("2026-01-01T00:00:00.000002Z"),
            Instant.parse("2026-01-01T00:00:00.000003Z"));

    PortfolioState back = roundTrip(state, PortfolioState.class);

    assertEquals(state.getPortfolioId(), back.getPortfolioId());
    assertEquals(state.getPositions().size(), back.getPositions().size());
    Position backPosition = back.getPositions().get(0);
    assertEquals(position.getPortfolioId(), backPosition.getPortfolioId());
    assertEquals(position.getInstrumentId(), backPosition.getInstrumentId());
    assertEquals(position.getQuantity(), backPosition.getQuantity());
    assertEquals(position.getAverageCost(), backPosition.getAverageCost());
    assertEquals(position.getAsOfEventTime(), backPosition.getAsOfEventTime());
    assertEquals(state.getEventTime(), back.getEventTime());
    assertEquals(state.getIngestTime(), back.getIngestTime());
  }

  @Test
  void portfolioStateKeyRoundTrips() throws Exception {
    PortfolioStateKey key = new PortfolioStateKey("portfolio-1");
    PortfolioStateKey back = roundTrip(key, PortfolioStateKey.class);
    assertEquals(key.getPortfolioId(), back.getPortfolioId());
  }
}
