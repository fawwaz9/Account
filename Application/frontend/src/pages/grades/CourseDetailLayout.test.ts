import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * The course page's order (owner, 2026-11-07): the grade columns and their actions, then past
 * students' figures beside the other grading schemes, then Delete Course alone, last. Read from
 * the page's source, since rendering the page needs every panel it holds.
 */

const page = readFileSync(join(__dirname, "CourseDetailPage.tsx"), "utf8");
const markup = page.slice(page.indexOf("return (\n    <div className=\"courseDetailPage\">"));

function at(marker: string): number {
  const index = markup.indexOf(marker);
  expect(index, marker).toBeGreaterThan(-1);
  return index;
}

describe("the course page's layout", () => {
  it("puts past students and the schemes side by side, after the grade columns and their actions", () => {
    const bottom = at('<div className="courseBottom">');
    expect(at('<div className="categoriesGrid">')).toBeLessThan(bottom);
    expect(at("If I drop it…")).toBeLessThan(bottom);
    const inside = markup.slice(bottom, at('<div className="courseDeleteRow">'));
    expect(inside).toContain("<ClassFigures");
    expect(inside).toContain("<GradingSchemes");
    expect(markup.match(/<ClassFigures/g)).toHaveLength(1);
    expect(markup.match(/<GradingSchemes/g)).toHaveLength(1);
  });

  it("leaves Delete Course alone at the very end, out of the other actions", () => {
    const row = at('<div className="courseDeleteRow">');
    expect(markup.match(/Delete Course\n/g)).toHaveLength(1);
    expect(markup.indexOf("Delete Course\n")).toBeGreaterThan(row);
    expect(at("<ClassFigures")).toBeLessThan(row);
    expect(at("<GradingSchemes")).toBeLessThan(row);
  });
});
