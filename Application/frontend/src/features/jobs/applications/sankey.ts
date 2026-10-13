import { Flow } from "./types";

/**
 * Where each stage sits, left to right. The path an application takes runs
 * through the first five; every outcome that ends one sits in the last column,
 * so a rejection after an interview and one straight after applying land in the
 * same place, the way recruiting-season Sankeys are drawn.
 */
export const COLUMNS: Record<string, number> = {
  applied: 0, screening: 1, interview: 2, offer: 3, accepted: 4,
  rejected: 4, no_reply: 4, withdrawn: 4, waiting: 4,
};

/** Top to bottom within the last column: the good news first. */
const ORDER = ["applied", "screening", "interview", "offer", "accepted", "waiting", "rejected", "no_reply", "withdrawn"];

export interface SankeyNode {
  id: string;
  column: number;
  x: number;
  y: number;
  height: number;
  /** Applications passing through: the larger of what comes in and goes out. */
  count: number;
}

export interface SankeyLink {
  source: string;
  target: string;
  count: number;
  /** The band's top edge where it leaves its source and where it reaches its target. */
  sourceY: number;
  targetY: number;
  thickness: number;
}

export interface SankeyLayout {
  nodes: SankeyNode[];
  links: SankeyLink[];
  width: number;
  height: number;
}

export const NODE_WIDTH = 12;
const GAP = 14;

/**
 * Lay the flows out as a Sankey: a node per stage, a band per flow, each as
 * thick as the applications it carries.
 *
 * Kept out of the component, like the week grid's overlap maths, because
 * positions go wrong silently: a band an inch off reads as a design choice.
 * One scale for every column, so a band's thickness means the same number of
 * applications wherever it is.
 */
export function layoutSankey(flows: Flow[], width: number, height: number): SankeyLayout {
  const live = flows.filter((flow) => flow.count > 0 && flow.source in COLUMNS && flow.target in COLUMNS);
  const inflow = new Map<string, number>();
  const outflow = new Map<string, number>();
  for (const flow of live) {
    outflow.set(flow.source, (outflow.get(flow.source) ?? 0) + flow.count);
    inflow.set(flow.target, (inflow.get(flow.target) ?? 0) + flow.count);
  }
  const ids = ORDER.filter((id) => inflow.has(id) || outflow.has(id));
  const count = (id: string) => Math.max(inflow.get(id) ?? 0, outflow.get(id) ?? 0);

  // The busiest column decides the scale, gaps included, so nothing overflows.
  const columns = new Map<number, string[]>();
  for (const id of ids) columns.set(COLUMNS[id], [...(columns.get(COLUMNS[id]) ?? []), id]);
  let scale = Infinity;
  for (const members of columns.values()) {
    const total = members.reduce((sum, id) => sum + count(id), 0);
    const room = height - GAP * (members.length - 1);
    if (total > 0) scale = Math.min(scale, room / total);
  }
  if (!Number.isFinite(scale)) scale = 0;

  const lastColumn = Math.max(0, ...ids.map((id) => COLUMNS[id]));
  const step = lastColumn === 0 ? 0 : (width - NODE_WIDTH) / lastColumn;
  const nodes = new Map<string, SankeyNode>();
  for (const [column, members] of columns) {
    let y = 0;
    for (const id of members) {
      const node = { id, column, x: column * step, y, height: count(id) * scale, count: count(id) };
      nodes.set(id, node);
      y += node.height + GAP;
    }
  }

  // Bands stack down each node's edge in the order of the stage they go to (or
  // come from), so they cross as little as a fixed order allows.
  const sourceOffset = new Map<string, number>();
  const targetOffset = new Map<string, number>();
  const links: SankeyLink[] = [...live]
    .sort((a, b) => ORDER.indexOf(a.target) - ORDER.indexOf(b.target) || ORDER.indexOf(a.source) - ORDER.indexOf(b.source))
    .map((flow) => {
      const source = nodes.get(flow.source)!;
      const target = nodes.get(flow.target)!;
      const thickness = flow.count * scale;
      const sourceY = source.y + (sourceOffset.get(flow.source) ?? 0);
      const targetY = target.y + (targetOffset.get(flow.target) ?? 0);
      sourceOffset.set(flow.source, (sourceOffset.get(flow.source) ?? 0) + thickness);
      targetOffset.set(flow.target, (targetOffset.get(flow.target) ?? 0) + thickness);
      return { source: flow.source, target: flow.target, count: flow.count, sourceY, targetY, thickness };
    });

  return { nodes: [...nodes.values()], links, width, height };
}

/** The SVG path of one band: a ribbon from its source's right edge to its target's left. */
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
