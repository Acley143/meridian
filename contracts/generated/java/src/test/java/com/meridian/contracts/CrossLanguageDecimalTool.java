package com.meridian.contracts;

import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import org.apache.avro.io.BinaryDecoder;
import org.apache.avro.io.BinaryEncoder;
import org.apache.avro.io.DecoderFactory;
import org.apache.avro.io.EncoderFactory;
import org.apache.avro.specific.SpecificDatumReader;
import org.apache.avro.specific.SpecificDatumWriter;

/**
 * Standalone CLI (not a JUnit test) for the cross-language decimal fidelity
 * test in contracts/tests/python/test_cross_language_decimal.py. That test
 * shells out to this tool -- Java and Python have no other shared process
 * to hand bytes through, so this is the deliberately narrow bridge between
 * them: encode a RiskSnapshot.price (the field we care about here, since
 * it is the one Decimal(38,8) field every one of contracts/avro's schemas
 * shares) to a file, or decode one and print the value back, so the Python
 * side can drive both directions and assert exact equality.
 *
 * Usage:
 *   write &lt;decimal-string&gt; &lt;output-file&gt;
 *     Encodes a RiskSnapshot with `price` set to the given decimal into
 *     `output-file` as raw Avro binary. Exits 0 on success.
 *   read &lt;input-file&gt; &lt;expected-decimal-string&gt;
 *     Decodes `input-file` as a RiskSnapshot and compares `price` against
 *     `expected-decimal-string` via BigDecimal.equals (exact scale AND
 *     value, per java.math.BigDecimal semantics). Prints the decoded value
 *     to stdout either way. Exits 0 if equal, 1 if not.
 */
public final class CrossLanguageDecimalTool {

  private CrossLanguageDecimalTool() {}

  private static RiskSnapshot fixtureWithPrice(BigDecimal price) {
    return new RiskSnapshot(
        "portfolio-1",
        Instant.parse("2026-01-01T00:00:00.000000Z"),
        "0.1.0",
        price,
        BigDecimal.ZERO,
        BigDecimal.ZERO,
        BigDecimal.ZERO,
        BigDecimal.ZERO,
        BigDecimal.ZERO,
        0.0,
        "scenario-1",
        Instant.parse("2026-01-01T00:00:00.000000Z"));
  }

  public static void main(String[] args) throws Exception {
    if (args.length < 1) {
      System.err.println("usage: write <decimal> <file> | read <file> <expected-decimal>");
      System.exit(2);
    }

    switch (args[0]) {
      case "write" -> {
        BigDecimal price = new BigDecimal(args[1]);
        RiskSnapshot snapshot = fixtureWithPrice(price);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        BinaryEncoder encoder = EncoderFactory.get().binaryEncoder(out, null);
        new SpecificDatumWriter<>(RiskSnapshot.class).write(snapshot, encoder);
        encoder.flush();
        Files.write(Path.of(args[2]), out.toByteArray());
        System.out.println("wrote " + args[2] + " price=" + price);
      }
      case "read" -> {
        byte[] bytes = Files.readAllBytes(Path.of(args[1]));
        BigDecimal expected = new BigDecimal(args[2]);
        BinaryDecoder decoder = DecoderFactory.get().binaryDecoder(bytes, null);
        RiskSnapshot snapshot = new SpecificDatumReader<>(RiskSnapshot.class).read(null, decoder);
        BigDecimal actual = snapshot.getPrice();
        System.out.println("decoded price=" + actual);
        if (!actual.equals(expected)) {
          System.err.println("MISMATCH: expected=" + expected + " actual=" + actual);
          System.exit(1);
        }
        System.out.println("MATCH");
      }
      default -> {
        System.err.println("unknown mode: " + args[0]);
        System.exit(2);
      }
    }
  }
}
