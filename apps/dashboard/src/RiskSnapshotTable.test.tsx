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

  it("renders a money string exactly, where parsing as a double would round it", () => {
    // 9007199254740993 = 2^53 + 1, the canonical integer a JS double cannot
    // represent -- Number() rounds it to 9007199254740994. Confirm the
    // premise, then confirm the render never took that path.
    const EXACT_PRICE = "9007199254740993.12345678";
    expect(Number(EXACT_PRICE).toString()).not.toBe(EXACT_PRICE);

    const html = renderToStaticMarkup(<RiskSnapshotTable snapshot={{ ...SNAPSHOT, price: EXACT_PRICE }} />);

    expect(html).toContain(EXACT_PRICE);
    expect(html).not.toContain("9007199254740994");
  });

  it("shows no stale marker by default", () => {
    const html = renderToStaticMarkup(<RiskSnapshotTable snapshot={SNAPSHOT} />);
    expect(html).not.toMatch(/stale/i);
  });

  it("shows a stale marker when stale=true", () => {
    const html = renderToStaticMarkup(<RiskSnapshotTable snapshot={SNAPSHOT} stale />);
    expect(html).toMatch(/stale/i);
  });

  it("renders the age of the oldest input, not just a boolean stale flag", () => {
    const html = renderToStaticMarkup(
      <RiskSnapshotTable
        snapshot={{
          ...SNAPSHOT,
          as_of: "2026-08-31T00:05:00.000Z",
          oldest_input_event_time: "2026-08-31T00:04:15.000Z", // 45s behind, under threshold
        }}
      />,
    );
    expect(html).toContain("Oldest input age");
    expect(html).toContain("45s");
  });

  it("marks the age row itself (not just the table caption) when stale", () => {
    const html = renderToStaticMarkup(
      <RiskSnapshotTable
        snapshot={{
          ...SNAPSHOT,
          as_of: "2026-08-31T00:05:00.000Z",
          oldest_input_event_time: "2026-08-31T00:00:00.000Z", // 5m behind, over threshold
        }}
        stale
      />,
    );
    expect(html).toContain("5m 0s");
    expect(html).toContain('class="stale"');
  });
});
