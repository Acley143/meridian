import { useEffect, useState } from "react";
import { getLatestRisk, type RiskSnapshot } from "./riskSnapshot";

const BASE_URL = import.meta.env.VITE_CORE_SERVICE_URL ?? "http://localhost:8080";

/**
 * "reopen" is distinct from "open": it's an open that follows a prior
 * error, so the UI can say "reconnected" instead of silently looking like
 * nothing happened.
 */
export type ConnectionStatus = "connecting" | "open" | "error" | "reopen";

export interface RiskStreamState {
  status: ConnectionStatus;
  /** Oldest first, i.e. arrival order -- the most recently arrived is last. */
  snapshots: RiskSnapshot[];
  /**
   * Set when the initial REST fetch or a resync-triggered refetch fails.
   * Cleared on the next successful fetch. A rendering consumer must show
   * this rather than leaving a blank/loading panel on failure.
   */
  fetchError: string | null;
}

function messageFromError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * Subscribes to a portfolio's SSE risk stream (ADR-0009), after an initial
 * REST fetch of the latest snapshot so the panel has something to render
 * before the first stream message arrives. Resume-on-reconnect is handled
 * by the browser's native EventSource (ADR-0012) -- no client code needed
 * for that part. A `resync` event means the requested replay exceeded the
 * server's bound, so this refetches full state via REST instead of
 * trusting a resumed stream to have covered the gap.
 */
export function useRiskStream(portfolioId: string): RiskStreamState {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [snapshots, setSnapshots] = useState<RiskSnapshot[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    setStatus("connecting");
    setSnapshots([]);
    setFetchError(null);
    let hasErrored = false;
    let cancelled = false;

    const fetchLatest = () => {
      getLatestRisk(portfolioId)
        .then((snapshot) => {
          if (cancelled) return;
          if (snapshot) {
            setFetchError(null);
            setSnapshots((prev) => [...prev, snapshot]);
          }
        })
        .catch((err: unknown) => {
          if (!cancelled) {
            setFetchError(messageFromError(err));
          }
        });
    };

    fetchLatest();

    const source = new EventSource(`${BASE_URL}/portfolios/${encodeURIComponent(portfolioId)}/risk/stream`);

    const handleMessage = (event: MessageEvent<string>) => {
      const snapshot = JSON.parse(event.data) as RiskSnapshot;
      setSnapshots((prev) => [...prev, snapshot]);
    };

    const handleOpen = () => {
      setStatus(hasErrored ? "reopen" : "open");
    };

    const handleError = () => {
      hasErrored = true;
      setStatus("error");
    };

    const handleResync = () => {
      fetchLatest();
    };

    source.addEventListener("message", handleMessage);
    source.addEventListener("open", handleOpen);
    source.addEventListener("error", handleError);
    source.addEventListener("resync", handleResync);

    return () => {
      cancelled = true;
      source.removeEventListener("message", handleMessage);
      source.removeEventListener("open", handleOpen);
      source.removeEventListener("error", handleError);
      source.removeEventListener("resync", handleResync);
      source.close();
    };
  }, [portfolioId]);

  return { status, snapshots, fetchError };
}
