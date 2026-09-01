import { useEffect, useState } from "react";
import { getLatestRisk, type RiskSnapshot } from "./riskSnapshot";

/**
 * The whole reason ADR-0012 exists is that a dropped connection otherwise
 * looks exactly like a quiet market -- so every one of these must be
 * distinguishable in the UI, not collapsed into a generic "not live":
 *
 * - "reconnecting" vs "failed" are both EventSource `error` events, told
 *   apart by `readyState`: CONNECTING (0) means the browser is retrying on
 *   its own (per ADR-0012, no client-side reconnect code needed); CLOSED (2)
 *   means it has given up and nothing will bring the stream back without a
 *   fresh subscription (e.g. remounting with a new portfolioId).
 * - "resyncing" is the client half of the resync guarantee: the stream said
 *   the gap was too big to replay, and this is the REST refetch in flight
 *   to close it.
 */
export type ConnectionStatus = "connecting" | "live" | "reconnecting" | "resyncing" | "failed";

/** EventSource.CLOSED, per spec -- not relied on as a static since the
 * global is stubbed out entirely in tests. */
const READY_STATE_CLOSED = 2;

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
    let cancelled = false;

    const fetchLatest = () => {
      return getLatestRisk(portfolioId)
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

    const source = new EventSource(`/api/v1/portfolios/${encodeURIComponent(portfolioId)}/risk/stream`);

    // After a resync refetch settles, the status should reflect the
    // connection's actual state right now (which may have changed while the
    // refetch was in flight), not be forced back to "live" unconditionally.
    const READY_STATE_CONNECTING = 0;
    const statusFromReadyState = (): "live" | "reconnecting" | "failed" => {
      if (source.readyState === READY_STATE_CLOSED) return "failed";
      if (source.readyState === READY_STATE_CONNECTING) return "reconnecting";
      return "live";
    };

    const handleMessage = (event: MessageEvent<string>) => {
      const snapshot = JSON.parse(event.data) as RiskSnapshot;
      setSnapshots((prev) => [...prev, snapshot]);
    };

    const handleOpen = () => {
      setStatus("live");
    };

    const handleError = () => {
      // A CONNECTING readyState here means the browser is retrying on its
      // own per ADR-0012; CLOSED means it has given up for good.
      setStatus(statusFromReadyState() === "failed" ? "failed" : "reconnecting");
    };

    const handleResync = () => {
      setStatus("resyncing");
      fetchLatest().then(() => {
        if (!cancelled) {
          setStatus(statusFromReadyState());
        }
      });
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
