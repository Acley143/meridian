package com.meridian.coreservice.audit;

import java.io.ByteArrayOutputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * The canonical form specification for {@code AuditEntry}, per docs/domain-model.md#auditentry's
 * "Canonical form" section and ADR-0008. Exactly three fields, in this fixed order: entry_id,
 * entry_type, payload -- length-prefixed (netstring-style: UTF-8 byte length as ASCII decimal
 * digits, then ':', then the UTF-8 bytes) to make the concatenation unambiguous. event_time,
 * ingest_time, and prev_hash are deliberately excluded -- see the domain model doc and ADR-0008's
 * editorial amendment for why that's a real, acknowledged scope limit, not an oversight.
 *
 * <p>Used by the write path ({@link AuditLogRepository}) only. {@link AuditChainVerifier}
 * deliberately does NOT call this class -- it reimplements the same specification independently, so
 * a bug here (e.g. a miscounted length prefix) doesn't get rubber-stamped by verification that
 * shares the buggy code.
 */
public final class CanonicalForm {

  private CanonicalForm() {}

  public static byte[] bytes(String entryId, String entryType, String payload) {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    writeField(out, entryId);
    writeField(out, entryType);
    writeField(out, payload);
    return out.toByteArray();
  }

  public static String sha256Hex(byte[] data) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hash = digest.digest(data);
      StringBuilder hex = new StringBuilder(hash.length * 2);
      for (byte b : hash) {
        hex.append(String.format("%02x", b));
      }
      return hex.toString();
    } catch (NoSuchAlgorithmException e) {
      // SHA-256 is guaranteed available on every JVM (JLS platform requirement) -- this can't
      // actually happen, but MessageDigest.getInstance's checked exception forces a handler.
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }

  private static void writeField(ByteArrayOutputStream out, String value) {
    byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);
    byte[] prefix = (Integer.toString(utf8.length) + ":").getBytes(StandardCharsets.US_ASCII);
    try {
      out.write(prefix);
      out.write(utf8);
    } catch (java.io.IOException e) {
      // ByteArrayOutputStream.write never actually throws IOException.
      throw new UncheckedIOException(e);
    }
  }
}
