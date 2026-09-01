import { describe, expect, it } from "vitest";
import { isStale } from "./staleness";

describe("isStale", () => {
  it("is not stale when oldest_input_event_time equals as_of", () => {
    expect(
      isStale({
        as_of: "2026-08-31T00:05:00.000Z",
        oldest_input_event_time: "2026-08-31T00:05:00.000Z",
      }),
    ).toBe(false);
  });

  it("is not stale for a small gap under the threshold", () => {
    expect(
      isStale({
        as_of: "2026-08-31T00:05:00.000Z",
        oldest_input_event_time: "2026-08-31T00:04:59.000Z",
      }),
    ).toBe(false);
  });

  it("is stale for a gap well over the threshold", () => {
    expect(
      isStale({
        as_of: "2026-08-31T00:05:00.000Z",
        oldest_input_event_time: "2026-08-31T00:00:00.000Z",
      }),
    ).toBe(true);
  });

  it("treats the epoch sentinel (unknown, pre-field producer) as stale", () => {
    expect(
      isStale({
        as_of: "2026-08-31T00:05:00.000Z",
        oldest_input_event_time: "1970-01-01T00:00:00.000Z",
      }),
    ).toBe(true);
  });
});
