import { describe, expect, it } from "vitest";
import { formatDecimal } from "./decimal";

describe("formatDecimal", () => {
  it("preserves scale-8 precision that a JS double cannot represent exactly", () => {
    // 0.1 + 0.2 !== 0.3 in IEEE-754; parseFloat/Number() on either input
    // would risk this class of corruption. Decimal must not.
    expect(formatDecimal("100000000000000000000000000000.12345678")).toBe(
      "100000000000000000000000000000.12345678",
    );
  });

  it("pads to 8 decimal places", () => {
    expect(formatDecimal("42")).toBe("42.00000000");
  });

  it("preserves sign", () => {
    expect(formatDecimal("-1.5")).toBe("-1.50000000");
  });
});
