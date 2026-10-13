import { Flow } from "./types";
import { STATUS_LABELS } from "./types";
import { bandPath, layoutSankey, NODE_WIDTH } from "./sankey";

const WIDTH = 640;
const HEIGHT = 240;

function label(id: string): string {
  return id === "waiting" ? "Waiting" : STATUS_LABELS[id as keyof typeof STATUS_LABELS] ?? id;
}

/**
 * Applications → interviews → offers, drawn from each application's history
 * (D2). Hand-drawn SVG, like the app's other charts, from a pure layout
 * (`sankey.ts`). The numbers are in the labels as well as the widths, so the
 * chart says what it shows without anyone measuring a band.
 */
export default function ApplicationSankey({ flows }: { flows: Flow[] }) {
  if (flows.length === 0) return null;
  const layout = layoutSankey(flows, WIDTH - 110, HEIGHT);

  return (
    <figure className="appSankey">
      <svg viewBox={`-4 -4 ${WIDTH + 8} ${HEIGHT + 8}`} role="img"
        aria-label={flows.map((flow) => `${label(flow.source)} to ${label(flow.target)}: ${flow.count}`).join("; ")}>
        {layout.links.map((link) => (
          <path key={`${link.source}-${link.target}`} d={bandPath(link, layout)}
            className={`appSankeyBand appSankeyBand-${link.target}`} />
        ))}
        {layout.nodes.map((node) => (
          <g key={node.id}>
            <rect x={node.x} y={node.y} width={NODE_WIDTH} height={Math.max(node.height, 2)}
              className={`appSankeyNode appSankeyNode-${node.id}`} />
            <text x={node.x + NODE_WIDTH + 6} y={node.y + Math.max(node.height, 2) / 2}
              dominantBaseline="middle" className="appSankeyLabel">
              {label(node.id)} {node.count}
            </text>
          </g>
        ))}
      </svg>
    </figure>
  );
}
