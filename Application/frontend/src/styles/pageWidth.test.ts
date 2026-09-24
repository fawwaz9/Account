import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * No page may fight `.container` over its own width.
 *
 * `globals.css` gives `.container` a `max-width: none`, deliberately, to defeat
 * the Tailwind utility of the same name that would otherwise clamp six pages.
 * A page stylesheet that also sets `max-width` on the class sitting beside
 * `container` on the same element is therefore in a tie: both unlayered, both
 * one class of specificity. Ties are broken by source order, and source order
 * here is whatever order the bundler happened to emit the files in -- a
 * function of the module graph, not of anything anybody wrote down.
 *
 * That is not hypothetical. `.budgetPage` and `.accountPage` each carried a
 * `max-width: 980px` that never applied, because globals.css was emitted after
 * them. Making the routes lazy changed the module graph, the order flipped, and
 * both pages went narrow -- a visible regression, in production, with no CSS
 * edited and `cssCodeSplit: false` already set to keep the stylesheet whole.
 * Keeping one file preserves the rule *set*, not the *order* within it, and
 * order is the only thing that breaks this kind of tie.
 *
 * So the rule is not "get the order right", which nobody can verify by reading:
 * it is "do not enter the tie at all". To genuinely clamp a page, put the width
 * on an inner wrapper that does not also carry `container`.
 *
 * Read from disk rather than through `import.meta.glob`. Vitest stubs every CSS
 * import as an empty string, so a glob over the stylesheets returns the right
 * filenames with no contents -- and a scan of empty strings finds no offenders
 * and passes. That happened while this file was being written; the third test
 * below is what caught it, and is why it is here.
 */

function walk(dir: string, keep: (file: string) => boolean): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    return statSync(full).isDirectory() ? walk(full, keep) : keep(entry) ? [full] : [];
  });
}

function readAll(dir: string, ext: string): Record<string, string> {
  return Object.fromEntries(
    walk(dir, (f) => f.endsWith(ext)).map((f) => [f, readFileSync(f, "utf8")]),
  );
}

const MARKUP = readAll("src", ".tsx");
const STYLES = readAll("src/styles", ".css");

/** Every class that appears alongside `container` in a className. */
function companionClasses(): string[] {
  const found = new Set<string>();
  for (const text of Object.values(MARKUP)) {
    for (const m of text.matchAll(/className="container([^"]*)"/g)) {
      for (const cls of m[1].trim().split(/\s+/).filter(Boolean)) found.add(cls);
    }
  }
  return [...found];
}

/** Does any stylesheet declare `max-width` in this class's own rule? */
function maxWidthRules(cls: string): string[] {
  const out: string[] = [];
  for (const [file, text] of Object.entries(STYLES)) {
    // The class's own rule only: not `.thing .inner {...}`, and not a media
    // query, both of which are free to set whatever they like.
    for (const m of text.matchAll(new RegExp(`\\.${cls}\\s*\\{([^}]*)\\}`, "g"))) {
      if (/(^|[;\s])max-width\s*:/.test(m[1])) out.push(`${file}: .${cls} { ${m[1].trim()} }`);
    }
  }
  return out;
}

describe("a page that shares an element with .container", () => {
  /**
   * The first control: the scan sees the files at all. Everything below reports
   * "nothing wrong", which is also what a scan of zero files reports.
   */
  it("is actually found by the scan", () => {
    expect(Object.keys(MARKUP).length).toBeGreaterThan(20);
    expect(Object.keys(STYLES).length).toBeGreaterThan(5);
    expect(companionClasses()).toContain("budgetPage");
    expect(companionClasses()).toContain("accountPage");
  });

  it("does not set its own max-width, which would be a tie broken by bundler order", () => {
    expect(companionClasses().flatMap(maxWidthRules)).toEqual([]);
  });

  /**
   * The second control, and the one that earns its place: it reads a file's
   * *contents*, so it fails if the stylesheets arrive as empty strings. Without
   * it the clause above passes while proving nothing, which is exactly what
   * happened once already.
   */
  it("has a detector that can see a max-width when there is one", () => {
    expect(maxWidthRules("container")).not.toEqual([]);
  });
});
