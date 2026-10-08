/**
 * Formats a float64 risk statistic (`var_95`) for display. This is not a
 * decimal cash amount (ADR-0004): `var_95` arrives as a JSON number, so
 * `formatDecimal` must not be used for it -- that function takes a
 * wire-format decimal string and claims scale-8 precision a float64 does not
 * have. Two decimals is a display choice for a magnitude, not a precision
 * claim.
 *
 * `Intl.NumberFormat` rather than `toFixed`, which switches to exponent
 * notation at 1e21 and above. A non-finite value renders "unavailable": the
 * UI must never throw, and never show NaN where a currency figure belongs.
 */
const TWO_DECIMALS = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  useGrouping: false,
});

export function formatRisk(value: number): string {
  if (!Number.isFinite(value)) {
    return "unavailable";
  }
  // `value === 0` is also true for -0, which Intl would otherwise render "-0.00".
  return TWO_DECIMALS.format(value === 0 ? 0 : value);
}
