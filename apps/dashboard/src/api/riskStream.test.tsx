// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRiskStream } from "./riskStream";
import type { RiskSnapshot } from "./riskSnapshot";

class MockEventSource extends EventTarget {
  static instances: MockEventSource[] = [];
  readonly url: string;
  closed = false;

  constructor(url: string) {
    super();
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }
}

function emitOpen(source: MockEventSource): void {
  source.dispatchEvent(new Event("open"));
}

function emitError(source: MockEventSource): void {
  source.dispatchEvent(new Event("error"));
}

function emitMessage(source: MockEventSource, snapshot: RiskSnapshot): void {
  source.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(snapshot) }));
}

function emitResync(source: MockEventSource): void {
  source.dispatchEvent(new Event("resync"));
}

function snapshot(overrides: Partial<RiskSnapshot> = {}): RiskSnapshot {
  return {
    portfolio_id: "p1",
    as_of: "2026-08-31T00:00:00.000Z",
    pricer_version: "v1",
    price: "100.00000000",
    cash_delta: "1.00000000",
    cash_gamma: "2.00000000",
    cash_vega: "3.00000000",
    cash_theta: "4.00000000",
    cash_rho: "5.00000000",
    var_95: 1,
    scenario_id: "s1",
    oldest_input_event_time: "2026-08-31T00:00:00.000Z",
    ingest_time: "2026-08-31T00:00:01.000Z",
    ...overrides,
  };
}

function Harness({ portfolioId }: { portfolioId: string }) {
  const { status, snapshots, fetchError } = useRiskStream(portfolioId);
  const latest = snapshots.at(-1);
  return (
    <div>
      <p data-testid="status">{status}</p>
      <p data-testid="count">{snapshots.length}</p>
      <p data-testid="latest-price">{latest?.price ?? ""}</p>
      <p data-testid="fetch-error">{fetchError ?? ""}</p>
    </div>
  );
}

function notFoundFetch() {
  return vi.fn(async (_url: string) => new Response(null, { status: 404 }));
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
  // Every mount now does an initial REST fetch (Task 6): default it to a
  // harmless 404 so tests that don't care about REST don't hit real
  // network or need their own stub.
  vi.stubGlobal("fetch", notFoundFetch());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useRiskStream", () => {
  it("renders snapshots as they arrive", () => {
    render(<Harness portfolioId="p1" />);
    const source = MockEventSource.instances[0]!;

    act(() => emitMessage(source, snapshot({ price: "1.00000000" })));
    act(() => emitMessage(source, snapshot({ price: "2.00000000" })));

    expect(screen.getByTestId("count").textContent).toBe("2");
    expect(screen.getByTestId("latest-price").textContent).toBe("2.00000000");
  });

  it("triggers a REST refetch on resync", async () => {
    const fetchMock = vi.fn(async (_url: string) => new Response(JSON.stringify(snapshot({ price: "9.00000000" })), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness portfolioId="p1" />);

    // Mount already triggers one initial REST fetch (Task 6); let it settle
    // before isolating the resync-triggered call.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const callsBeforeResync = fetchMock.mock.calls.length;

    const source = MockEventSource.instances[0]!;
    act(() => emitResync(source));

    // The point of this test is that the network call itself happened, not
    // just that the "resync" handler ran -- a handler that no-ops silently
    // would still "run" and pass a weaker assertion.
    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBe(callsBeforeResync + 1);
    });
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("/portfolios/p1/risk");

    await waitFor(() => {
      expect(screen.getByTestId("latest-price").textContent).toBe("9.00000000");
    });
  });

  it("renders a fetch error rather than staying blank when the initial REST fetch fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string) => new Response(null, { status: 500, statusText: "Internal Server Error" })),
    );

    render(<Harness portfolioId="p1" />);

    await waitFor(() => {
      expect(screen.getByTestId("fetch-error").textContent).not.toBe("");
    });
    expect(screen.getByTestId("count").textContent).toBe("0");
  });

  it("transitions connection state through open, error, and reopen", () => {
    render(<Harness portfolioId="p1" />);
    const source = MockEventSource.instances[0]!;

    expect(screen.getByTestId("status").textContent).toBe("connecting");

    act(() => emitOpen(source));
    expect(screen.getByTestId("status").textContent).toBe("open");

    act(() => emitError(source));
    expect(screen.getByTestId("status").textContent).toBe("error");

    act(() => emitOpen(source));
    expect(screen.getByTestId("status").textContent).toBe("reopen");
  });

  it("closes the EventSource on unmount", () => {
    const { unmount } = render(<Harness portfolioId="p1" />);
    const source = MockEventSource.instances[0]!;

    expect(source.closed).toBe(false);
    unmount();
    expect(source.closed).toBe(true);
  });
});
