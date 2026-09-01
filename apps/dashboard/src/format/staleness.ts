import type { RiskSnapshot } from "../api/riskSnapshot";

/**
 * Q1 placeholder: no ADR or docs/nfr-budget.md line pins an exact staleness
 * budget yet. Chosen generously relative to the 250ms tick-to-render p99 so
 * this flags a genuinely stalled input feed, not ordinary market quiet.
 */
const STALE_THRESHOLD_MS = 30_000;

/**
 * True when oldest_input_event_time trails as_of by more than the
 * staleness threshold -- including the epoch sentinel (ADR: see
 * docs/domain-model.md#risksnapshot), which by construction trails any
 * real as_of by far more than the threshold and is correctly treated as
 * stale: it means "unknown," and unknown can't be proven live.
 */
export function isStale(snapshot: Pick<RiskSnapshot, "as_of" | "oldest_input_event_time">): boolean {
  const asOfMs = new Date(snapshot.as_of).getTime();
  const oldestInputMs = new Date(snapshot.oldest_input_event_time).getTime();
  return asOfMs - oldestInputMs > STALE_THRESHOLD_MS;
}
