import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * One stylesheet, so a class name is app-wide whatever file it is written in.
 *
 * `build.cssCodeSplit` is false, so every `styles/*.css` is concatenated into a
 * single file and a bare class selector reaches every page. Two files defining
 * the same name are therefore in a cascade fight decided by whichever the
 * bundler emitted last -- and the loser is usually a page whose author never
 * saw the other file.
 *
 * That is not hypothetical. `.categoryList` is the budget's "Where it went"
 * list *and* the grade-category list on a course page. The budget rules landed
 * later, so grade rows were inset from their own border, given a second
 * separator, shrunk a step and spaced apart -- a visible break on a page
 * nothing in budget.css mentions.
 *
 * The fix is to scope, not to re-order: source order here is a property of the
 * module graph, not of anything anybody wrote down. This test names the
 * offenders rather than forbidding all sharing, because a few names are shared
 * deliberately.
 */

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return walk(full);
    return entry.endsWith(".css") ? [full] : [];
  });
}

const SHEETS = Object.fromEntries(
  walk("src/styles").map((f) => [f, readFileSync(f, "utf8")]),
);

/**
 * Class names this file defines as a **bare** selector -- `.thing {` or
 * `.thing, .other {`, but not `.scope .thing` or `.thing .inner`, which are
 * already scoped and cannot collide the same way.
 */
function bareClasses(css: string): Set<string> {
  const found = new Set<string>();
  // Strip comments first: prose mentioning a class name is not a definition.
  const code = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of code.matchAll(/(^|[,{}])\s*\.([A-Za-z][\w-]*)\s*(?=[,{])/g)) {
    found.add(m[2]);
  }
  return found;
}

/**
 * Deliberately shared, and safe: these are the app's own primitives, defined
 * once and used everywhere. Anything else appearing twice is an accident.
 */
const SHARED_ON_PURPOSE = new Set<string>([]);

describe("a class name defined in two stylesheets", () => {
  /** The control. A scan that reads nothing reports no collisions either. */
  it("is looked for across every stylesheet", () => {
    expect(Object.keys(SHEETS).length).toBeGreaterThan(5);
    expect(bareClasses(SHEETS["src/styles/budget.css"]).size).toBeGreaterThan(20);
  });

  /** And the detector finds a name that really is there. */
  it("has a detector that recognises a real class", () => {
    expect(bareClasses(SHEETS["src/styles/budget.css"])).toContain("categorySpend");
  });

  it("does not exist", () => {
    const owners: Record<string, string[]> = {};
    for (const [file, css] of Object.entries(SHEETS)) {
      for (const name of bareClasses(css)) {
        if (SHARED_ON_PURPOSE.has(name)) continue;
        (owners[name] ??= []).push(file);
      }
    }

    const clashes = Object.entries(owners)
      .filter(([, files]) => files.length > 1)
      .map(([name, files]) => `.${name} in ${files.join(" and ")}`);

    expect(clashes).toEqual([]);
  });
});
