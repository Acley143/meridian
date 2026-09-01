import { afterEach, describe, expect, it, vi } from "vitest";
import { getLatestRisk, type RiskSnapshot } from "./riskSnapshot";

const SNAPSHOT: RiskSnapshot = {
  portfolio_id: "p1",
  as_of: "2026-08-31T00:00:00.000Z",
  pricer_version: "v1",
  price: "100000000000000000000000000000.12345678",
  cash_delta: "1.00000000",
  cash_gamma: "2.00000000",
  cash_vega: "3.00000000",
  cash_theta: "4.00000000",
  cash_rho: "5.00000000",
  var_95: 42,
  scenario_id: "s1",
  oldest_input_event_time: "2026-08-31T00:00:00.000Z",
  ingest_time: "2026-08-31T00:00:01.000Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getLatestRisk", () => {
  it("returns the parsed snapshot on 200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(SNAPSHOT), { status: 200 })),
    );

    await expect(getLatestRisk("p1")).resolves.toEqual(SNAPSHOT);
  });

  it("returns null on 404 (no snapshot yet)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 404 })),
    );

    await expect(getLatestRisk("p1")).resolves.toBeNull();
  });

  it("throws on other non-OK statuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 500, statusText: "Internal Server Error" })),
    );

    await expect(getLatestRisk("p1")).rejects.toThrow(/500/);
  });
});
