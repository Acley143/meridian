// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRiskStream } from "./riskStream";
import type { RiskSnapshot } from "./riskSnapshot";

const READY_STATE_CONNECTING = 0;
const READY_STATE_OPEN = 1;
const READY_STATE_CLOSED = 2;

class MockEventSource extends EventTarget {
  static instances: MockEventSource[] = [];
  readonly url: string;
  closed = false;
  readyState = READY_STATE_CONNECTING;

  constructor(url: string) {
    super();
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close(): void {
    this.closed = true;
    this.readyState = READY_STATE_CLOSED;
  }
}

function emitOpen(source: MockEventSource): void {
  source.readyState = READY_STATE_OPEN;
  source.dispatchEvent(new Event("open"));
}

/** A browser-retried error: the browser keeps readyState at CONNECTING and
 * will attempt to reconnect on its own. */
function emitTransientError(source: MockEventSource): void {
  source.readyState = READY_STATE_CONNECTING;
  source.dispatchEvent(new Event("error"));
}

/** A terminal error: the browser has given up, readyState is CLOSED. */
function emitFatalError(source: MockEventSource): void {
  source.readyState = READY_STATE_CLOSED;
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
    emitOpen(source);
    act(() => emitResync(source));

    // A resync must be visible as its own status, not silently folded into
    // "live" -- otherwise a dropped-and-resynced connection looks identical
    // to one that never had a gap.
    expect(screen.getByTestId("status").textContent).toBe("resyncing");

    // The point of this test is that the network call itself happened, not
    // just that the "resync" handler ran -- a handler that no-ops silently
    // would still "run" and pass a weaker assertion.
    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBe(callsBeforeResync + 1);
    });
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("/api/v1/portfolios/p1/risk");

    await waitFor(() => {
      expect(screen.getByTestId("latest-price").textContent).toBe("9.00000000");
    });
    // Once the refetch settles, status reflects the still-open connection.
    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("live");
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

  it("transitions connection state through connecting, live, and reconnecting", () => {
    render(<Harness portfolioId="p1" />);
    const source = MockEventSource.instances[0]!;

    expect(screen.getByTestId("status").textContent).toBe("connecting");

    act(() => emitOpen(source));
    expect(screen.getByTestId("status").textContent).toBe("live");

    // A CONNECTING readyState on error means the browser is retrying on its
    // own -- distinct from a terminal failure.
    act(() => emitTransientError(source));
    expect(screen.getByTestId("status").textContent).toBe("reconnecting");

    act(() => emitOpen(source));
    expect(screen.getByTestId("status").textContent).toBe("live");
  });

  it("shows a terminal failure distinctly from a browser-retried reconnect", () => {
    render(<Harness portfolioId="p1" />);
    const source = MockEventSource.instances[0]!;

    act(() => emitOpen(source));
    act(() => emitFatalError(source));

    expect(screen.getByTestId("status").textContent).toBe("failed");
  });

  it("closes the EventSource on unmount", () => {
    const { unmount } = render(<Harness portfolioId="p1" />);
    const source = MockEventSource.instances[0]!;

    expect(source.closed).toBe(false);
    unmount();
    expect(source.closed).toBe(true);
  });
});
