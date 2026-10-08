import { describe, expect, it } from "vitest";
import { formatRisk } from "./risk";

describe("formatRisk", () => {
  it("rounds a representative value to 2 decimal places", () => {
    expect(formatRisk(3228.5840156462987)).toBe("3228.58");
  });

  it("pads a whole number to 2 decimal places", () => {
    expect(formatRisk(42)).toBe("42.00");
  });

  it("renders zero as 0.00, including negative zero", () => {
    expect(formatRisk(0)).toBe("0.00");
    expect(formatRisk(-0)).toBe("0.00");
  });

  it("renders a non-finite value as unavailable, never NaN or Infinity", () => {
    expect(formatRisk(Number.NaN)).toBe("unavailable");
    expect(formatRisk(Number.POSITIVE_INFINITY)).toBe("unavailable");
    expect(formatRisk(Number.NEGATIVE_INFINITY)).toBe("unavailable");
  });

  it("renders a large value without exponent notation", () => {
    // (1e21).toFixed(2) is "1e+21"; the formatter must not take that path.
    expect(formatRisk(1e21)).toBe("1000000000000000000000.00");
  });
});
