import type { RiskSnapshot } from "../api/riskSnapshot";

/**
 * Q1 placeholder: no ADR or docs/nfr-budget.md line pins an exact staleness
 * budget yet. Chosen generously relative to the 250ms tick-to-render p99 so
 * this flags a genuinely stalled input feed, not ordinary market quiet.
 */
const STALE_THRESHOLD_MS = 30_000;

/**
 * How far the oldest contributing input price trails this snapshot's own
 * as_of -- deliberately measured against as_of, not wall-clock now(), since
 * as_of is scenario-derived event time (ADR-0011) that can legitimately
 * diverge from wall clock. "Age" here means "how stale relative to the
 * snapshot's own notion of now," matching the age-bound reasoning in
 * ADR-0012's editorial amendment.
 */
export function inputAgeMs(snapshot: Pick<RiskSnapshot, "as_of" | "oldest_input_event_time">): number {
  const asOfMs = new Date(snapshot.as_of).getTime();
  const oldestInputMs = new Date(snapshot.oldest_input_event_time).getTime();
  return asOfMs - oldestInputMs;
}

/**
 * True when oldest_input_event_time trails as_of by more than the
 * staleness threshold -- including the epoch sentinel (ADR: see
 * docs/domain-model.md#risksnapshot), which by construction trails any
 * real as_of by far more than the threshold and is correctly treated as
 * stale: it means "unknown," and unknown can't be proven live.
 */
export function isStale(snapshot: Pick<RiskSnapshot, "as_of" | "oldest_input_event_time">): boolean {
  return inputAgeMs(snapshot) > STALE_THRESHOLD_MS;
}

/** Human-readable rendering of {@link inputAgeMs}, e.g. "5s", "2m 15s", "1h 3m". */
export function formatInputAge(snapshot: Pick<RiskSnapshot, "as_of" | "oldest_input_event_time">): string {
  const totalSeconds = Math.max(0, Math.round(inputAgeMs(snapshot) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}
