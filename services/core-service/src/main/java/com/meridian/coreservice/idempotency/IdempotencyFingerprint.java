package com.meridian.coreservice.idempotency;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * ADR-0023: the fingerprint is a hash of the raw request bytes exactly as received, never a
 * canonicalized/re-serialized form -- a genuine retry sends byte-identical content, and
 * canonicalization adds a component (the canonicalizer itself) that can diverge from what the
 * client actually sent, in either direction. Deliberately independent of {@code
 * audit.CanonicalForm} -- that class hashes a fixed, named tuple of audit fields under its own
 * specification; this hashes an opaque byte blob under a different one. Sharing the code would
 * couple two concerns that only coincidentally both use SHA-256.
 */
public final class IdempotencyFingerprint {

  private IdempotencyFingerprint() {}

  public static String sha256Hex(byte[] rawRequestBytes) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hash = digest.digest(rawRequestBytes);
      StringBuilder hex = new StringBuilder(hash.length * 2);
      for (byte b : hash) {
        hex.append(String.format("%02x", b));
      }
      return hex.toString();
    } catch (NoSuchAlgorithmException e) {
      // SHA-256 is guaranteed available on every JVM (JLS platform requirement).
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }
}
