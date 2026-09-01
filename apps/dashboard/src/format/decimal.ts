import Decimal from "decimal.js";

/**
 * Formats a wire-format decimal string (precision 38, scale 8, ADR-0013) for
 * display. Never `parseFloat`/`Number()` this: an IEEE-754 double can't
 * represent scale-8 decimals exactly and would silently corrupt the value.
 */
export function formatDecimal(value: string): string {
  return new Decimal(value).toFixed(8);
}
