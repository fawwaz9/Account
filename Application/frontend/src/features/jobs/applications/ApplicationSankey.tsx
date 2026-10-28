import { Flow, STATUS_LABELS } from "./types";
import { bandPath, kindOf, layoutSankey, NODE_WIDTH, totals } from "./sankey";
import HelpTip from "../../../shared/components/HelpTip";

/** Chart width, in viewBox units; the layout leaves 120 for labels. */
const WIDTH = 640;
/** Chart height, in viewBox units. */
const HEIGHT = 260;

/** Display name for a node id: its status label, or "Waiting". */
function label(id: string): string {
  const kind = kindOf(id);
  return kind === "waiting" ? "Waiting" : STATUS_LABELS[kind as keyof typeof STATUS_LABELS] ?? kind;
}

/**
 * Where applications went, as a tree of bands that never cross.
 * Counts appear in the labels, the legend and the accessible name, not only in widths.
 */
export default function ApplicationSankey({ flows }: { flows: Flow[] }) {
  const layout = layoutSankey(flows, WIDTH - 120, HEIGHT);
  if (layout.nodes.length === 0) return null;
  const sums = totals(flows);
  const legend = sums.map((item) => `${label(item.kind)} ${item.count}`).join(" · ");
  const bottom = Math.max(...layout.nodes.map((node) => node.y + node.height));

  return (
    <figure className="appSankey">
      <svg viewBox={`-4 -8 ${WIDTH + 8} ${bottom + 16}`} role="img"
        aria-label={[
          ...layout.links.map((link) => `${label(link.source)} to ${label(link.target)}: ${link.count}`),
          `In all: ${legend}`,
        ].join("; ")}>
        {layout.links.map((link) => (
          <path key={`${link.source}-${link.target}`} d={bandPath(link, layout)}
            className={`appSankeyBand appSankeyBand-${kindOf(link.target)}`} />
        ))}
        {layout.nodes.map((node) => (
          <g key={node.id}>
            <rect x={node.x} y={node.y} width={NODE_WIDTH} height={Math.max(node.height, 2)}
              className={`appSankeyNode appSankeyNode-${node.kind}`} />
            <text x={node.x + NODE_WIDTH + 6} y={node.y + Math.max(node.height, 2) / 2}
              dominantBaseline="middle" className="appSankeyLabel">
              {label(node.id)} {node.count}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="appSankeyLegend">
        <span>In all: {legend}</span>
        <HelpTip label="How to read this chart">
          Each stage counts every application that got at least that far, so one that went straight to an
          interview is counted under Screening too. Under each stage are the ones that ended there.
        </HelpTip>
      </figcaption>
    </figure>
  );
}
