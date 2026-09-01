import { useRiskStream, type ConnectionStatus } from "./api/riskStream";
import { RiskSnapshotTable } from "./RiskSnapshotTable";
import { formatDecimal } from "./format/decimal";
import { isStale } from "./format/staleness";

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
  resyncing: "Resyncing…",
  failed: "Connection failed",
};

export function LiveRiskPanel({ portfolioId }: { portfolioId: string }) {
  const { status, snapshots, fetchError } = useRiskStream(portfolioId);
  const latest = snapshots.at(-1) ?? null;

  return (
    <section>
      <p data-testid="connection-status" aria-live="polite">
        {STATUS_LABEL[status]}
      </p>

      {fetchError && <p role="alert">Failed to load risk data: {fetchError}</p>}

      {latest ? (
        <RiskSnapshotTable snapshot={latest} stale={isStale(latest)} />
      ) : (
        !fetchError && <p>Waiting for a snapshot…</p>
      )}

      <h2>History</h2>
      <table>
        <thead>
          <tr>
            <th scope="col">as_of</th>
            <th scope="col">price</th>
          </tr>
        </thead>
        <tbody>
          {snapshots
            .map((snapshot, index) => ({ snapshot, index }))
            .reverse()
            .map(({ snapshot, index }) => (
              <tr key={`${snapshot.as_of}-${index}`}>
                <td>{snapshot.as_of}</td>
                <td>{formatDecimal(snapshot.price)}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </section>
  );
}
