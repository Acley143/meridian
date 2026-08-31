package com.meridian.coreservice.audit;

/**
 * Standalone entry point used only by {@code CanonicalFormStabilityTest} to prove {@link
 * CanonicalForm} produces byte-identical output across a real, separate JVM process, not merely
 * across in-memory objects within one process. Not used by the running service.
 *
 * <p>Usage: {@code java -cp <classpath> com.meridian.coreservice.audit.CanonicalFormCli <entryId>
 * <entryType> <payload>} -- prints the resulting {@code entry_hash} hex string to stdout.
 */
public final class CanonicalFormCli {

  private CanonicalFormCli() {}

  public static void main(String[] args) {
    if (args.length != 3) {
      System.err.println("usage: CanonicalFormCli <entryId> <entryType> <payload>");
      System.exit(2);
    }
    String hash = CanonicalForm.sha256Hex(CanonicalForm.bytes(args[0], args[1], args[2]));
    System.out.print(hash);
  }
}
