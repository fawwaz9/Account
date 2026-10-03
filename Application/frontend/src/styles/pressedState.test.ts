import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Every button acknowledges being pressed.
 *
 * `:active` appeared **zero times** in the whole stylesheet, across 192 buttons —
 * so the only feedback a press ever had was `:hover`, which touch devices do not
 * have at all. Tapping anything on a phone did nothing visible until the request
 * came back.
 *
 * jsdom has no cascade and no layout, so a component test cannot see any of this.
 * Reading the stylesheets is the only way to assert it, which is why this sits
 * beside the other cascade guards rather than next to a component.
 */

const STYLES = join(__dirname);

function allCss(dir: string): { file: string; text: string }[] {
  const out: { file: string; text: string }[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...allCss(path));
    else if (entry.endsWith(".css")) out.push({ file: path, text: readFileSync(path, "utf8") });
  }
  return out;
}

const sheets = allCss(STYLES);
const everything = sheets.map((s) => s.text).join("\n");

describe("pressed states", () => {
  it("exist at all", () => {
    // The regression this file is here to catch: it was zero once.
    expect(everything).toMatch(/:active/);
  });

  it("cover every button through a bare element selector", () => {
    // The buttons are not on one shared class — `.buttons` carries 19 of 192 and
    // `.calButton` 64 — so a class-only rule would leave most of the app silent.
    expect(everything).toMatch(/button:not\(:disabled\):active/);
  });

  it("cover the two classes whose own hover would outrank the baseline", () => {
    // `.class:hover` is (0,2,0) and `button:active` is (0,1,1), and you are always
    // hovering while pressing — so any class with a hover movement needs its own
    // `:active` or the baseline never shows.
    expect(everything).toMatch(/\.buttons:not\(:disabled\):active/);
    expect(everything).toMatch(/\.calButton:not\(:disabled\):active/);
  });

  it("never fire a pressed state on a disabled button", () => {
    // A disabled control that presses is a lie about what the click will do.
    const actives = everything.match(/^[^\n{]*:active[^\n{]*\{/gm) ?? [];
    expect(actives.length).toBeGreaterThan(0);
    for (const selector of actives) {
      expect(selector).toMatch(/:not\(:disabled\)|:disabled/);
    }
  });

  it("drop the movement for anyone who asked for reduced motion", () => {
    // The brightness change carries the same message without the transform, so the
    // acknowledgement survives the preference rather than being removed by it.
    const reduced = everything.match(
      /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/g,
    );
    expect(reduced, "no reduced-motion block found").toBeTruthy();
    expect(reduced!.join("\n")).toMatch(/:active/);
    expect(reduced!.join("\n")).toMatch(/transform:\s*none/);
  });
});
