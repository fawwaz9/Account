import { describe, expect, it } from "vitest";
import { bandPath, layoutSankey, NODE_WIDTH } from "./sankey";
import { Flow } from "./types";

/** The Sankey's layout: positions go wrong silently, so they are pinned here. */

const FLOWS: Flow[] = [
  { source: "applied", target: "interview", count: 4 },
  { source: "applied", target: "rejected", count: 10 },
  { source: "applied", target: "waiting", count: 6 },
  { source: "interview", target: "offer", count: 2 },
  { source: "interview", target: "rejected", count: 2 },
  { source: "offer", target: "accepted", count: 1 },
  { source: "offer", target: "withdrawn", count: 1 },
];

describe("the Sankey layout", () => {
  const layout = layoutSankey(FLOWS, 500, 200);
  const node = (id: string) => layout.nodes.find((n) => n.id === id)!;

  it("has a node per stage that appears, and none for one that does not", () => {
    expect(layout.nodes.map((n) => n.id).sort()).toEqual(
      ["accepted", "applied", "interview", "offer", "rejected", "waiting", "withdrawn"]);
    expect(layout.nodes.find((n) => n.id === "screening")).toBeUndefined();
  });

  it("counts each stage as what passes through it", () => {
    expect(node("applied").count).toBe(20);
    expect(node("interview").count).toBe(4);
    expect(node("rejected").count).toBe(12);
  });

  it("puts every outcome in the last column, wherever it was reached from", () => {
    expect(node("rejected").column).toBe(4);
    expect(node("accepted").column).toBe(4);
    expect(node("waiting").column).toBe(4);
    expect(node("applied").x).toBe(0);
    expect(node("rejected").x).toBe(500 - NODE_WIDTH);
  });

  it("uses one scale everywhere, so a band's thickness means the same count in any column", () => {
    const perApplication = node("applied").height / 20;
    for (const link of layout.links) {
      expect(link.thickness).toBeCloseTo(link.count * perApplication, 6);
    }
  });

  it("never runs past the bottom, gaps included", () => {
    for (const n of layout.nodes) expect(n.y + n.height).toBeLessThanOrEqual(200 + 1e-9);
  });

  it("stacks the bands leaving a node down its edge without overlap", () => {
    const leaving = layout.links.filter((link) => link.source === "applied").sort((a, b) => a.sourceY - b.sourceY);
    for (let i = 1; i < leaving.length; i += 1) {
      expect(leaving[i].sourceY).toBeCloseTo(leaving[i - 1].sourceY + leaving[i - 1].thickness, 6);
    }
    const last = leaving[leaving.length - 1];
    expect(last.sourceY + last.thickness).toBeCloseTo(node("applied").y + node("applied").height, 6);
  });

  it("draws a closed ribbon from the source's right edge to the target's left", () => {
    const link = layout.links.find((l) => l.source === "applied" && l.target === "interview")!;
    const path = bandPath(link, layout);
    expect(path.startsWith(`M${NODE_WIDTH},`)).toBe(true);
    expect(path.endsWith("Z")).toBe(true);
  });

  it("draws nothing from no flows", () => {
    expect(layoutSankey([], 500, 200).nodes).toEqual([]);
  });
});
