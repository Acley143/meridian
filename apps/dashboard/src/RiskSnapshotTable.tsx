import type { RiskSnapshot } from "./api/riskSnapshot";
import { formatDecimal } from "./format/decimal";
import { formatRisk } from "./format/risk";
import { formatInputAge } from "./format/staleness";

const CASH_GREEK_ROWS = [
  { label: "Cash delta", field: "cash_delta" },
  { label: "Cash gamma", field: "cash_gamma" },
  { label: "Cash vega", field: "cash_vega" },
  { label: "Cash theta", field: "cash_theta" },
  { label: "Cash rho", field: "cash_rho" },
] as const satisfies readonly { label: string; field: keyof RiskSnapshot }[];

/**
 * One line for the whole table: every figure in it (price, the cash Greeks,
 * VaR) is denominated in base_currency. An empty string is the "unknown"
 * sentinel (ADR-0028 Decision 2) and never means any particular currency, so
 * there is no default to fall back to.
 */
function currencyLine(baseCurrency: string): string {
  return baseCurrency ? `Figures in ${baseCurrency}` : "Figures in an unknown currency";
}

export function RiskSnapshotTable({ snapshot, stale = false }: { snapshot: RiskSnapshot; stale?: boolean }) {
  return (
    <>
      <p>{currencyLine(snapshot.base_currency)}</p>
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
          <tr>
            <th scope="row">VaR (1-day, 95%)</th>
            <td>{formatRisk(snapshot.var_95)}</td>
          </tr>
          {/*
            var_95 of 0.0 means "not computed" from pricer_version 0.1.0 and a
            zero-volatility book from 0.2.0 onward (ADR-0029); the number alone
            cannot tell them apart. Showing the version lets a reader do so
            without the view hard-coding any version check.
          */}
          <tr>
            <th scope="row">Pricer version</th>
            <td>{snapshot.pricer_version}</td>
          </tr>
        </tbody>
      </table>
    </>
  );
}
