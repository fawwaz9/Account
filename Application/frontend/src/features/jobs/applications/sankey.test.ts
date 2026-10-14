import { describe, expect, it } from "vitest";
import { bandPath, layoutSankey, NODE_WIDTH, SankeyLayout, throughStages, totals } from "./sankey";
import { Flow } from "./types";

/**
 * The tracker's Sankey as a tree (D8): each stage splits straight into the
 * next stage and the ways applications ended there, so no band crosses
 * another. Positions go wrong silently, so they are pinned here.
 */

/** The test account's "summer 26" season, as the API returned it on 2026-10-14. */
const SEASON: Flow[] = [
  { source: "applied", target: "no_reply", count: 59 }, { source: "applied", target: "rejected", count: 56 },
  { source: "applied", target: "screening", count: 29 }, { source: "screening", target: "interview", count: 17 },
  { source: "interview", target: "rejected", count: 11 }, { source: "screening", target: "rejected", count: 8 },
  { source: "applied", target: "withdrawn", count: 6 }, { source: "screening", target: "no_reply", count: 4 },
  { source: "interview", target: "no_reply", count: 2 }, { source: "interview", target: "offer", count: 2 },
  { source: "interview", target: "withdrawn", count: 2 }, { source: "offer", target: "accepted", count: 1 },
  { source: "offer", target: "withdrawn", count: 1 },
];

const node = (layout: SankeyLayout, id: string) => layout.nodes.find((n) => n.id === id)!;

describe("skipped stages (D8)", () => {
  it("are drawn through: applied straight to interview passes through screening", () => {
    const steps = throughStages([{ source: "applied", target: "interview", count: 3 },
      { source: "interview", target: "rejected", count: 3 }]);
    expect(steps).toEqual(expect.arrayContaining([
      { source: "applied", target: "screening", count: 3 },
      { source: "screening", target: "interview", count: 3 },
      { source: "interview", target: "rejected@interview", count: 3 },
    ]));
    expect(steps.find((s) => s.source === "applied" && s.target === "interview")).toBeUndefined();
  });

  it("add to the stage they pass through rather than replacing it", () => {
    const steps = throughStages([
      { source: "applied", target: "screening", count: 5 }, { source: "applied", target: "offer", count: 1 },
    ]);
    expect(steps.find((s) => s.source === "applied" && s.target === "screening")?.count).toBe(6);
    expect(steps.find((s) => s.source === "interview" && s.target === "offer")?.count).toBe(1);
  });

  it("leave every stage balanced: what comes in goes out", () => {
    const steps = throughStages([...SEASON, { source: "applied", target: "interview", count: 2 },
      { source: "interview", target: "waiting", count: 2 }]);
    for (const stage of ["screening", "interview", "offer"]) {
      const inflow = steps.filter((s) => s.target === stage).reduce((n, s) => n + s.count, 0);
      const outflow = steps.filter((s) => s.source === stage).reduce((n, s) => n + s.count, 0);
      expect(outflow, stage).toBe(inflow);
    }
  });
});

describe("the tree", () => {
  const layout = layoutSankey(SEASON, 500, 260);

  it("has the season's stages, each counting everyone who got that far", () => {
    expect([150, 29, 17, 2, 1]).toEqual(
      ["applied", "screening", "interview", "offer", "accepted"].map((id) => node(layout, id).count));
  });

  it("gives each outcome its own node at the stage it happened", () => {
    expect(node(layout, "rejected@applied").count).toBe(56);
    expect(node(layout, "rejected@screening").count).toBe(8);
    expect(node(layout, "rejected@interview").count).toBe(11);
    expect(node(layout, "withdrawn@offer").count).toBe(1);
    expect(layout.nodes.find((n) => n.id === "rejected")).toBeUndefined();
  });

  it("sends every band exactly one column", () => {
    for (const link of layout.links) {
      expect(node(layout, link.target).column, `${link.source}->${link.target}`).toBe(node(layout, link.source).column + 1);
    }
  });

  it("puts the next stage first in its column, along the top", () => {
    for (const stage of ["screening", "interview", "offer", "accepted"]) {
      const n = node(layout, stage);
      expect(n.y, stage).toBe(0);
      const below = layout.nodes.filter((other) => other.column === n.column && other.id !== stage);
      for (const other of below) expect(other.y).toBeGreaterThan(n.y);
    }
  });

  it("orders outcomes under a stage: waiting, rejected, no reply, withdrawn", () => {
    const column1 = layout.nodes.filter((n) => n.column === 1).sort((a, b) => a.y - b.y).map((n) => n.id);
    expect(column1).toEqual(["screening", "rejected@applied", "no_reply@applied", "withdrawn@applied"]);
  });

  it("never crosses: bands leaving one column keep their order where they arrive", () => {
    for (const a of layout.links) {
      for (const b of layout.links) {
        if (a === b || node(layout, a.source).column !== node(layout, b.source).column) continue;
        const startsAbove = a.sourceY < b.sourceY;
        const endsAbove = a.targetY < b.targetY;
        expect(endsAbove, `${a.source}->${a.target} against ${b.source}->${b.target}`).toBe(startsAbove);
      }
    }
  });

  it("stacks a stage's bands down its edge, without gaps or overlap", () => {
    const leaving = layout.links.filter((l) => l.source === "applied").sort((x, y) => x.sourceY - y.sourceY);
    for (let i = 1; i < leaving.length; i += 1) {
      expect(leaving[i].sourceY).toBeCloseTo(leaving[i - 1].sourceY + leaving[i - 1].thickness, 6);
    }
    const last = leaving[leaving.length - 1];
    expect(last.sourceY + last.thickness).toBeCloseTo(node(layout, "applied").height, 6);
  });

  it("uses one scale everywhere, so thickness means the same count in any column", () => {
    const perApplication = node(layout, "applied").height / 150;
    for (const link of layout.links) expect(link.thickness).toBeCloseTo(link.count * perApplication, 6);
  });

  it("stays inside the height, gaps included", () => {
    for (const n of layout.nodes) expect(n.y + n.height).toBeLessThanOrEqual(260 + 1e-9);
  });

  it("draws a closed ribbon from a source's right edge", () => {
    const link = layout.links.find((l) => l.source === "applied" && l.target === "screening")!;
    const path = bandPath(link, layout);
    expect(path.startsWith(`M${NODE_WIDTH},0`)).toBe(true);
    expect(path.endsWith("Z")).toBe(true);
  });

  it("draws nothing from no flows", () => {
    expect(layoutSankey([], 500, 260).nodes).toEqual([]);
  });
});

describe("the legend's totals", () => {
  it("sum each outcome across every stage, with accepted first", () => {
    expect(totals(SEASON)).toEqual([
      { kind: "accepted", count: 1 }, { kind: "rejected", count: 75 },
      { kind: "no_reply", count: 65 }, { kind: "withdrawn", count: 9 },
    ]);
  });
});
