import type { RiskSnapshot } from "./api/riskSnapshot";
import { formatDecimal } from "./format/decimal";
import { formatInputAge } from "./format/staleness";

const CASH_GREEK_ROWS = [
  { label: "Cash delta", field: "cash_delta" },
  { label: "Cash gamma", field: "cash_gamma" },
  { label: "Cash vega", field: "cash_vega" },
  { label: "Cash theta", field: "cash_theta" },
  { label: "Cash rho", field: "cash_rho" },
] as const satisfies readonly { label: string; field: keyof RiskSnapshot }[];

export function RiskSnapshotTable({ snapshot, stale = false }: { snapshot: RiskSnapshot; stale?: boolean }) {
  return (
    <table>
      {stale && (
        <caption role="status">Stale — oldest input price is more than the staleness threshold behind as_of</caption>
      )}
      <tbody>
        <tr>
          <th scope="row">Price</th>
          <td>{formatDecimal(snapshot.price)}</td>
        </tr>
        <tr className={stale ? "stale" : undefined}>
          <th scope="row">Oldest input age</th>
          <td>
            {formatInputAge(snapshot)}
            {stale && " (stale)"}
          </td>
        </tr>
        {CASH_GREEK_ROWS.map(({ label, field }) => (
          <tr key={field}>
            <th scope="row">{label}</th>
            <td>{formatDecimal(snapshot[field])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
