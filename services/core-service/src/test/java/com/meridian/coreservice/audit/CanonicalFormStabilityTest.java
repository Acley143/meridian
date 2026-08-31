package com.meridian.coreservice.audit;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

/**
 * Canonical form is stable across processes (ADR-0008 Task 4.3). Spawns a genuinely separate JVM
 * process running {@link CanonicalFormCli} -- not just a fresh object or a second thread in this
 * same JVM -- so this cannot pass by accident on in-memory object identity or a JVM-instance-local
 * cache. Compares that subprocess's output to an independent in-process computation of the same
 * logical row.
 */
class CanonicalFormStabilityTest {

  @Test
  void subprocessAndInProcessComputationsAgree() throws IOException, InterruptedException {
    String entryId = "stability-test-entry";
    String entryType = "trade_booked";
    String payload = "{\"portfolio_id\":\"PF-1\",\"quantity\":\"100.00000000\"}";

    String inProcessHash =
        CanonicalForm.sha256Hex(CanonicalForm.bytes(entryId, entryType, payload));

    String subprocessHash = runCanonicalFormCliInSeparateProcess(entryId, entryType, payload);

    assertThat(subprocessHash).isEqualTo(inProcessHash);
    assertThat(subprocessHash).hasSize(64); // hex-encoded SHA-256
  }

  @Test
  void repeatedIndependentInProcessComputationsAreByteIdentical() {
    String entryId = "stability-test-entry-2";
    String entryType = "risk_snapshot_produced";
    String payload = "{\"as_of\":\"2026-08-31T00:00:00.000000Z\"}";

    // Fresh byte arrays and fresh String objects each time -- not the same reused instance --
    // to rule out an accidental dependency on Java's string interning or object identity rather
    // than on the actual byte content.
    String first =
        CanonicalForm.sha256Hex(
            CanonicalForm.bytes(
                new String(entryId.toCharArray()),
                new String(entryType.toCharArray()),
                new String(payload.toCharArray())));
    String second =
        CanonicalForm.sha256Hex(
            CanonicalForm.bytes(
                new String(entryId.toCharArray()),
                new String(entryType.toCharArray()),
                new String(payload.toCharArray())));

    assertThat(first).isEqualTo(second);
  }

  private String runCanonicalFormCliInSeparateProcess(
      String entryId, String entryType, String payload) throws IOException, InterruptedException {
    String javaBin = System.getProperty("java.home") + "/bin/java";
    String classpath = System.getProperty("java.class.path");

    Process process =
        new ProcessBuilder(
                javaBin,
                "-cp",
                classpath,
                "com.meridian.coreservice.audit.CanonicalFormCli",
                entryId,
                entryType,
                payload)
            .redirectErrorStream(false)
            .start();

    String output;
    try (BufferedReader reader =
        new BufferedReader(
            new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
      output = reader.readLine();
    }

    boolean finished = process.waitFor(30, TimeUnit.SECONDS);
    assertThat(finished).as("CanonicalFormCli subprocess did not exit in time").isTrue();
    assertThat(process.exitValue()).as("CanonicalFormCli subprocess exit code").isEqualTo(0);

    return output;
  }
}
