import { Flow } from "./types";

/** The stage chain, left to right; a stage counts everyone who got at least that far. */
export const STAGES = ["applied", "screening", "interview", "offer", "accepted"] as const;

/** How an application ended at a stage, top to bottom under it. */
export const OUTCOMES = ["waiting", "rejected", "no_reply", "withdrawn"] as const;

/** One stage of the chain. */
type Stage = (typeof STAGES)[number];
/** One way an application ended. */
type Outcome = (typeof OUTCOMES)[number];

/** True for a stage id. */
const isStage = (id: string): id is Stage => (STAGES as readonly string[]).includes(id);
/** True for an outcome id. */
const isOutcome = (id: string): id is Outcome => (OUTCOMES as readonly string[]).includes(id);

/** A drawn node: a stage, or an outcome at a stage. */
export interface SankeyNode {
  /** A stage, or an outcome at its stage such as "rejected@interview". */
  id: string;
  /** Stage or outcome name, for its label and colour. */
  kind: string;
  column: number;
  x: number;
  y: number;
  height: number;
  count: number;
}

/** A drawn band between two nodes. */
export interface SankeyLink {
  source: string;
  target: string;
  count: number;
  /** Top edge where the band leaves its source. */
  sourceY: number;
  /** Top edge where the band reaches its target. */
  targetY: number;
  thickness: number;
}

/** Positioned nodes and bands for the chart. */
export interface SankeyLayout {
  nodes: SankeyNode[];
  links: SankeyLink[];
  width: number;
  height: number;
}

/** Node bar width, px. */
export const NODE_WIDTH = 12;
/** Vertical gap between siblings in a column, px. */
const GAP = 14;

/** Kind part of a node id: "rejected@interview" gives "rejected". */
export const kindOf = (id: string) => id.split("@")[0];

/**
 * Flows as one-column steps: a skipped stage is drawn passed through.
 * Outcome edges are renamed for their stage, as in "rejected@interview".
 */
export function throughStages(flows: Flow[]): Flow[] {
  const counts = new Map<string, number>();
  const add = (source: string, target: string, count: number) => {
    const key = `${source}>${target}`;
    counts.set(key, (counts.get(key) ?? 0) + count);
  };
  for (const flow of flows) {
    if (flow.count <= 0 || !isStage(flow.source)) continue;
    const from = STAGES.indexOf(flow.source);
    if (isStage(flow.target)) {
      const to = STAGES.indexOf(flow.target);
      for (let at = from; at < to; at += 1) add(STAGES[at], STAGES[at + 1], flow.count);
    } else if (isOutcome(flow.target)) {
      add(flow.source, `${flow.target}@${flow.source}`, flow.count);
    }
  }
  return [...counts].map(([key, count]) => {
    const [source, target] = key.split(">");
    return { source, target, count };
  });
}

/** Legend counts: accepted and each outcome, summed across stages, zeros dropped. */
export function totals(flows: Flow[]): { kind: string; count: number }[] {
  const steps = throughStages(flows);
  const sum = (kind: string) =>
    steps.filter((step) => kindOf(step.target) === kind).reduce((n, step) => n + step.count, 0);
  return ["accepted", ...OUTCOMES]
    .map((kind) => ({ kind, count: sum(kind) }))
    .filter((item) => item.count > 0);
}

/**
 * Lay the flows out as a tree: each stage splits into the next stage, then its outcomes.
 * One scale everywhere, and every band spans one column, so none can cross.
 */
export function layoutSankey(flows: Flow[], width: number, height: number): SankeyLayout {
  const steps = throughStages(flows);
  if (steps.length === 0) return { nodes: [], links: [], width, height };

  const childrenOf = (stage: Stage) => {
    const next = STAGES[STAGES.indexOf(stage) + 1];
    const order = [next, ...OUTCOMES.map((outcome) => `${outcome}@${stage}`)];
    return order
      .map((id) => ({ id, count: steps.find((s) => s.source === stage && s.target === id)?.count ?? 0 }))
      .filter((child) => child.id && child.count > 0);
  };

  // Which stages have children, in chain order: each makes the next column.
  const parents = STAGES.filter((stage) => childrenOf(stage).length > 0);
  const appliedCount = childrenOf("applied").reduce((n, child) => n + child.count, 0);

  // The busiest column, gaps included, sets the one scale.
  let scale = appliedCount > 0 ? height / appliedCount : 0;
  for (const parent of parents) {
    const children = childrenOf(parent);
    const total = children.reduce((n, child) => n + child.count, 0);
    scale = Math.min(scale, (height - GAP * (children.length - 1)) / total);
  }

  const lastColumn = Math.max(...parents.map((parent) => STAGES.indexOf(parent) + 1));
  const step = (width - NODE_WIDTH) / lastColumn;
  const nodes = new Map<string, SankeyNode>();
  nodes.set("applied", {
    id: "applied", kind: "applied", column: 0, x: 0, y: 0, height: appliedCount * scale, count: appliedCount,
  });

  const links: SankeyLink[] = [];
  for (const parent of parents) {
    const from = nodes.get(parent);
    if (!from) continue;
    const column = STAGES.indexOf(parent) + 1;
    let childY = from.y;
    let leaving = from.y;
    for (const child of childrenOf(parent)) {
      const thickness = child.count * scale;
      nodes.set(child.id, {
        id: child.id, kind: kindOf(child.id), column, x: column * step, y: childY,
        height: thickness, count: child.count,
      });
      links.push({ source: parent, target: child.id, count: child.count, sourceY: leaving, targetY: childY, thickness });
      leaving += thickness;
      childY += thickness + GAP;
    }
  }

  return { nodes: [...nodes.values()], links, width, height };
}

/** SVG path for one band: a ribbon from its source's right edge to its target's left. */
export function bandPath(link: SankeyLink, layout: SankeyLayout): string {
  const source = layout.nodes.find((node) => node.id === link.source)!;
  const target = layout.nodes.find((node) => node.id === link.target)!;
  const x0 = source.x + NODE_WIDTH;
  const x1 = target.x;
  const mid = (x0 + x1) / 2;
  const top0 = link.sourceY;
  const top1 = link.targetY;
  const bottom0 = top0 + link.thickness;
  const bottom1 = top1 + link.thickness;
  return [
    `M${x0},${top0}`,
    `C${mid},${top0} ${mid},${top1} ${x1},${top1}`,
    `L${x1},${bottom1}`,
    `C${mid},${bottom1} ${mid},${bottom0} ${x0},${bottom0}`,
    "Z",
  ].join(" ");
}
