// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveRiskPanel } from "./LiveRiskPanel";
import type { RiskSnapshot } from "./api/riskSnapshot";

class MockEventSource extends EventTarget {
  static instances: MockEventSource[] = [];
  constructor(_url: string) {
    super();
    MockEventSource.instances.push(this);
  }
  close(): void {}
}

function emitMessage(source: MockEventSource, snapshot: RiskSnapshot): void {
  source.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(snapshot) }));
}

function snapshot(overrides: Partial<RiskSnapshot> = {}): RiskSnapshot {
  return {
    portfolio_id: "p1",
    as_of: "2026-08-31T00:05:00.000Z",
    pricer_version: "v1",
    price: "100.00000000",
    cash_delta: "1.00000000",
    cash_gamma: "2.00000000",
    cash_vega: "3.00000000",
    cash_theta: "4.00000000",
    cash_rho: "5.00000000",
    var_95: 1,
    scenario_id: "s1",
    oldest_input_event_time: "2026-08-31T00:05:00.000Z",
    ingest_time: "2026-08-31T00:05:01.000Z",
    ...overrides,
  };
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LiveRiskPanel staleness", () => {
  it("renders a live snapshot without a stale marker", () => {
    render(<LiveRiskPanel portfolioId="p1" />);
    const source = MockEventSource.instances[0]!;

    act(() => emitMessage(source, snapshot()));

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("renders a snapshot with an old oldest_input_event_time as stale", () => {
    render(<LiveRiskPanel portfolioId="p1" />);
    const source = MockEventSource.instances[0]!;

    act(() =>
      emitMessage(
        source,
        snapshot({
          as_of: "2026-08-31T00:05:00.000Z",
          oldest_input_event_time: "2026-08-31T00:00:00.000Z", // 5 minutes behind as_of
        }),
      ),
    );

    expect(screen.getByRole("status").textContent).toMatch(/stale/i);
  });
});
