package com.meridian.coreservice.web;

/**
 * Thrown only for a malformed {@code Last-Event-ID} header (ADR-0012 Task 4.3) -- see {@link
 * SseController} and {@link SseEventId#parse}.
 *
 * <p>Deliberately its own type rather than a bare {@link IllegalArgumentException}: {@link
 * GlobalExceptionHandler} maps only this type to {@code 400}. A bare {@code
 * IllegalArgumentException} is a common, generic exception thrown all over the JDK and Spring
 * internals for reasons that have nothing to do with a malformed client request -- mapping it
 * application-wide meant any such exception, anywhere, silently rendered as a client-fault 400 with
 * an internal message in the body, rather than surfacing as the server fault it actually was. (This
 * is exactly what hid the {@code lastHeartbeatSecondsAgo} null-detail bug -- see ADR-0022's
 * editorial amendments.)
 */
public class MalformedLastEventIdException extends IllegalArgumentException {

  public MalformedLastEventIdException(String message) {
    super(message);
  }

  public MalformedLastEventIdException(String message, Throwable cause) {
    super(message, cause);
  }
}
