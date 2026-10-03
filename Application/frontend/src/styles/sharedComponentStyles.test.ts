import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * A shared component's styles live somewhere every page actually has.
 *
 * `cssCodeSplit: false` makes one stylesheet in production, so a rule written in any
 * file reaches every page. Development is different: the dev server injects CSS per
 * *imported module*, so a rule only exists on pages whose module graph reaches that
 * file. A component used everywhere, whose rules sit in a page sheet nothing global
 * imports, is then styled in production and unstyled in development — the worse way
 * round, because the broken one is the one you look at while working.
 *
 * Three homes are safe, and the first is easy to miss: `main.tsx` imports several
 * sheets directly, which makes them global in both modes. A component may also
 * import its own sheet, which travels with it (`ErrorBoundary` does). What is not
 * safe is a page sheet nothing global reaches.
 */

const STYLES = __dirname;
const SHARED = join(STYLES, "..", "shared", "components");

function cssFiles(dir: string): { name: string; text: string }[] {
  const out: { name: string; text: string }[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...cssFiles(path));
    else if (entry.endsWith(".css")) out.push({ name: entry, text: readFileSync(path, "utf8") });
  }
  return out;
}

/** Class names a shared component puts in its own markup. */
function classesUsedBy(file: string): string[] {
  const text = readFileSync(join(SHARED, file), "utf8");
  return [
    ...new Set(
      (text.match(/className="([^"{}]+)"/g) ?? [])
        .flatMap((m) => m.replace(/className="|"/g, "").split(/\s+/))
        .filter((c) => c && !/^(small-text|muted|srOnly)$/.test(c)),
    ),
  ];
}

const sheets = cssFiles(STYLES);
const globals = sheets.find((s) => s.name === "globals.css")!;

/** Sheets `main.tsx` imports directly, so every page has them in dev too. */
const GLOBAL_SHEETS = new Set(
  [...readFileSync(join(STYLES, "..", "main.tsx"), "utf8")
    .matchAll(/import "\.\/styles\/(?:[\w-]+\/)?([\w.-]+\.css)"/g)].map((m) => m[1]),
);

describe("shared component styles", () => {
  it("knows which sheets are global, so the sweep below is not vacuous", () => {
    expect(globals, "globals.css not found").toBeTruthy();
    expect(GLOBAL_SHEETS.has("globals.css")).toBe(true);
    expect(GLOBAL_SHEETS.size, "main.tsx imports more than globals.css").toBeGreaterThan(1);
  });

  it("styles HelpTip from globals.css, not from a page's sheet", () => {
    for (const cls of ["helpTip", "helpTipMark", "helpTipPanel"]) {
      const inGlobals = new RegExp(`\\.${cls}[\\s:,\\[{>]`).test(globals.text);
      expect(inGlobals, `.${cls} should be defined in globals.css`).toBe(true);

      const elsewhere = sheets
        .filter((s) => s.name !== "globals.css")
        .filter((s) => new RegExp(`\\.${cls}[\\s:,\\[{>]`).test(s.text))
        .map((s) => s.name);
      expect(elsewhere, `.${cls} is also defined in ${elsewhere.join(", ")}`).toEqual([]);
    }
  });

  it("styles every shared class from globals.css or the component's own sheet", () => {
    // Catches the next component that grows a class and puts the rule in a page
    // sheet. Unstyled-only-in-dev is a slow, confusing bug to chase.
    const offenders: string[] = [];
    for (const file of readdirSync(SHARED).filter((f) => /\.tsx$/.test(f) && !f.includes(".test."))) {
      const source = readFileSync(join(SHARED, file), "utf8");
      // A sheet the component imports itself travels with it, so it is safe.
      const own = [...source.matchAll(/import "[^"]*\/([\w.-]+\.css)"/g)].map((m) => m[1]);
      for (const cls of classesUsedBy(file)) {
        const pattern = new RegExp(`\\.${cls}[\\s:,\\[{>]`);
        if (pattern.test(globals.text)) continue;
        const where = sheets
          .filter((s) => pattern.test(s.text))
          .map((s) => s.name)
          .filter((name) => !own.includes(name) && !GLOBAL_SHEETS.has(name));
        if (where.length > 0) offenders.push(`${file}: .${cls} is styled in ${where.join(", ")}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
