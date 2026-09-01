import { describe, expect, it } from "vitest";
import { formatInputAge, isStale } from "./staleness";

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

describe("formatInputAge", () => {
  it("formats sub-minute gaps in seconds", () => {
    expect(
      formatInputAge({
        as_of: "2026-08-31T00:05:00.000Z",
        oldest_input_event_time: "2026-08-31T00:04:45.000Z",
      }),
    ).toBe("15s");
  });

  it("formats multi-minute gaps as minutes and seconds", () => {
    expect(
      formatInputAge({
        as_of: "2026-08-31T00:05:00.000Z",
        oldest_input_event_time: "2026-08-31T00:00:00.000Z",
      }),
    ).toBe("5m 0s");
  });

  it("formats multi-hour gaps as hours and minutes", () => {
    expect(
      formatInputAge({
        as_of: "2026-08-31T02:05:00.000Z",
        oldest_input_event_time: "2026-08-31T00:00:00.000Z",
      }),
    ).toBe("2h 5m");
  });
});
