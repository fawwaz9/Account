import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * The row stacks; the line inside it spreads.
 *
 * "Where it went" put `justify-content: space-between` on the `li` itself,
 * which is right while a row is exactly two spans. Giving a row a progress bar
 * and a note broke it two ways at once: three children spread sideways instead
 * of stacking, and a row with no bar shrank its single child to its content, so
 * the name and amount sat together on the left with nothing to push against.
 *
 * Every test passed through all of that and it shipped. jsdom has no layout
 * engine, so nothing that renders the component can see it -- the markup was
 * correct and the cascade was not. What is checkable is the invariant the fix
 * rests on, which is what this asserts.
 */

const CSS = readFileSync("src/styles/budget.css", "utf8");

/** The declarations inside one top-level rule. */
function rule(selector: string): string {
  const m = CSS.match(new RegExp(`\\${selector}\\s*\\{([^}]*)\\}`));
  return m ? m[1] : "";
}

describe("a category row", () => {
  /** The control: the selectors exist and are being read at all. */
  it("is described by the stylesheet", () => {
    expect(CSS.length).toBeGreaterThan(1000);
    expect(rule(".categoryTop")).not.toBe("");
    expect(rule(".categorySpend .categoryList li")).not.toBe("");
  });

  it("stacks its children rather than spreading them", () => {
    expect(rule(".categorySpend .categoryList li")).toMatch(/flex-direction:\s*column/);
  });

  it("spreads the name and the amount across the full line", () => {
    const top = rule(".categoryTop");

    expect(top).toMatch(/justify-content:\s*space-between/);
    expect(top).toMatch(/width:\s*100%/);
  });

  /**
   * An editable amount is a `.plannedFigure` button and a plain one is a bare
   * span. Unless both carry the same padding the column of figures does not
   * line up, and the rows that differ are the quiet ones -- Uncategorised, and
   * every row on the budget page.
   */
  it("pads the amount the same whether or not it is a button", () => {
    const pad = (r: string) => r.match(/padding:\s*([^;]+)/)?.[1]?.trim();

    expect(pad(rule(".categoryAmount"))).toBe(pad(rule(".plannedFigure")));
  });
});
