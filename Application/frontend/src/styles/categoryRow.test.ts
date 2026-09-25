import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * The row stacks; the line inside it spreads.
 *
 * "Where it went" put `justify-content: space-between` directly on the `li`,
 * which was right while a row was exactly two spans. Giving a row a progress
 * bar and a note underneath broke it in two ways at once: three children spread
 * along the row instead of stacking, and on a row with *no* bar the single
 * remaining child shrank to its content, so the name and the amount sat
 * together on the left with the space-between pushing against nothing.
 *
 * Every one of the 127 tests passed through all of that, and it shipped. jsdom
 * has no layout engine, so nothing that renders the component can see it -- the
 * markup was correct the whole time and the cascade was not. What is checkable
 * is the invariant the fix rests on, which is what this asserts.
 */

const CSS = readFileSync("src/styles/budget.css", "utf8");

/** The declarations inside one top-level rule. */
function rule(selector: string): string {
  const m = CSS.match(new RegExp(`\\${selector}\\s*\\{([^}]*)\\}`));
  return m ? m[1] : "";
}

describe("a category row", () => {
  /** The control: these selectors exist and are being read. */
  it("is described by the stylesheet at all", () => {
    expect(CSS.length).toBeGreaterThan(1000);
    expect(rule(".categoryTop")).not.toBe("");
    expect(rule(".categoryList li")).not.toBe("");
  });

  /**
   * The `li` must stack. If it is a row again, its own children -- the top
   * line, the bar, the note -- spread sideways, which is the original bug.
   */
  it("stacks its children rather than spreading them", () => {
    expect(rule(".categoryList li")).toMatch(/flex-direction:\s*column/);
  });

  /**
   * And the line inside it must spread, across the full width. Without the
   * width it is free to shrink to its content and the amount never reaches the
   * right-hand edge -- which looks like `space-between` simply not working.
   */
  it("spreads the name and the amount across the full line", () => {
    const top = rule(".categoryTop");

    expect(top).toMatch(/justify-content:\s*space-between/);
    expect(top).toMatch(/width:\s*100%/);
  });

  /**
   * An editable amount is a `.plannedFigure` button and a plain one is a bare
   * span. Unless both carry the same padding the column of figures does not
   * line up, and the rows that differ are the quiet ones -- Uncategorised, and
   * every row on the account detail page.
   */
  it("pads the amount the same whether or not it is a button", () => {
    const pad = (r: string) => r.match(/padding:\s*([^;]+)/)?.[1]?.trim();

    expect(pad(rule(".categoryAmount"))).toBe(pad(rule(".plannedFigure")));
  });
});
