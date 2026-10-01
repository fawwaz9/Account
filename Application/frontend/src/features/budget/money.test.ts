import { describe, expect, it } from "vitest";
import { formatMoney, formatPercent } from "./money";

/**
 * `formatMoney` renders through `toLocaleString` with no fixed locale, so it
 * follows whatever machine it runs on. These assertions are deliberately
 * written to hold in any locale -- they pin the decisions this module actually
 * makes (the sign, the currency mark, two decimals, the compact form) rather
 * than one locale's choice of separator, which is not this module's to make.
 */
describe("formatMoney", () => {
  it("always shows two decimals", () => {
    expect(formatMoney(0)).toMatch(/^\$0\D00$/);
    expect(formatMoney(12.5)).toMatch(/^\$12\D50$/);
    expect(formatMoney(12)).toMatch(/^\$12\D00$/);
  });

  /**
   * A real minus sign, U+2212, not the hyphen on the keyboard. It is the
   * difference between "−$5.00" reading as an amount and reading as a list
   * item, and it is the kind of detail that gets "fixed" back to a hyphen by
   * someone retyping the line.
   */
  it("negates with a minus sign rather than a hyphen", () => {
    const rendered = formatMoney(-5);

    expect(rendered.startsWith("−")).toBe(true);
    expect(rendered.startsWith("-")).toBe(false);
    expect(rendered).toMatch(/^−\$5\D00$/);
  });

  it("puts the sign outside the currency mark, not inside it", () => {
    // "−$5.00", never "$−5.00".
    expect(formatMoney(-5).indexOf("−")).toBeLessThan(formatMoney(-5).indexOf("$"));
  });

  describe("signed", () => {
    it("marks a positive amount too, which the default does not", () => {
      expect(formatMoney(5, { signed: true })).toMatch(/^\+\$5\D00$/);
      expect(formatMoney(5)).toMatch(/^\$5\D00$/);
    });

    it("still uses the minus sign for a negative", () => {
      expect(formatMoney(-5, { signed: true })).toMatch(/^−\$5\D00$/);
    });

    it("treats zero as positive rather than inventing a sign for it", () => {
      expect(formatMoney(0, { signed: true })).toMatch(/^\+\$0\D00$/);
    });
  });

  /**
   * The compact form exists for chart axes, where a four-figure tick with two
   * decimals collides with its neighbour. It drops cents on purpose.
   */
  describe("compact", () => {
    it("drops cents below a thousand", () => {
      expect(formatMoney(999, { compact: true })).toBe("$999");
      expect(formatMoney(12.5, { compact: true })).toBe("$13");
    });

    it("uses thousands above a thousand, with one decimal under ten", () => {
      expect(formatMoney(1234.5, { compact: true })).toMatch(/^\$1\D2k$/);
      expect(formatMoney(9999, { compact: true })).toMatch(/^\$10k$/);
    });

    it("drops the decimal once there are ten thousands or more", () => {
      expect(formatMoney(12345, { compact: true })).toMatch(/^\$12k$/);
    });

    it("keeps the sign rules it has everywhere else", () => {
      expect(formatMoney(-1234.5, { compact: true })).toMatch(/^−\$1\D2k$/);
      expect(formatMoney(1234.5, { compact: true, signed: true })).toMatch(/^\+\$1\D2k$/);
    });
  });
});

describe("formatPercent", () => {
  it("renders a gain with an explicit plus when asked", () => {
    expect(formatPercent(3.2, { signed: true })).toBe("+3.2%");
  });

  it("renders a loss with a minus, which is the case this exists for", () => {
    // A percentage that can only come out positive is the bug a returns feature
    // always ships with.
    expect(formatPercent(-8.1, { signed: true })).toBe("−8.1%");
  });

  it("uses the same minus character as formatMoney, not a hyphen", () => {
    // They sit next to each other on the account page. U+2212, both of them.
    expect(formatPercent(-8.1)).toContain("−");
    expect(formatPercent(-8.1)).not.toContain("-");
    expect(formatMoney(-8.1)[0]).toBe(formatPercent(-8.1)[0]);
  });

  it("omits the plus unless asked, so a bare figure reads as a quantity", () => {
    expect(formatPercent(3.2)).toBe("3.2%");
  });

  it("keeps one decimal, including on a whole number", () => {
    expect(formatPercent(5)).toBe("5.0%");
  });

  it("rounds to one decimal rather than printing what it was given", () => {
    expect(formatPercent(3.26)).toBe("3.3%");
  });

  it("treats zero the way formatMoney does, as non-negative", () => {
    // Arguably zero is neither a gain nor a loss, but `formatMoney(0, {signed})`
    // is "+$0.00", and the two appear side by side. Matching it beats being
    // separately clever.
    expect(formatPercent(0, { signed: true })).toBe("+0.0%");
    expect(formatMoney(0, { signed: true })[0]).toBe(formatPercent(0, { signed: true })[0]);
  });
});
