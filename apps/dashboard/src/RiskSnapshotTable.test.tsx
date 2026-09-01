import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { RiskSnapshot } from "./api/riskSnapshot";
import { RiskSnapshotTable } from "./RiskSnapshotTable";

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

describe("RiskSnapshotTable", () => {
  it("renders price and all five cash Greeks at full scale-8 precision", () => {
    const html = renderToStaticMarkup(<RiskSnapshotTable snapshot={SNAPSHOT} />);

    expect(html).toContain("100000000000000000000000000000.12345678");
    expect(html).toContain("1.00000000");
    expect(html).toContain("2.00000000");
    expect(html).toContain("3.00000000");
    expect(html).toContain("4.00000000");
    expect(html).toContain("5.00000000");
  });

  it("shows no stale marker by default", () => {
    const html = renderToStaticMarkup(<RiskSnapshotTable snapshot={SNAPSHOT} />);
    expect(html).not.toMatch(/stale/i);
  });

  it("shows a stale marker when stale=true", () => {
    const html = renderToStaticMarkup(<RiskSnapshotTable snapshot={SNAPSHOT} stale />);
    expect(html).toMatch(/stale/i);
  });
});
