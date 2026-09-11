import { TermPoint } from "../types";

interface GradeTrendChartProps {
  readonly points: readonly TermPoint[];
}

// Drawn by hand rather than pulling in a charting library for one chart on one
// page. The viewBox scales to its container; a long degree scrolls sideways
// instead of squashing.
const WIDTH = 460;
const HEIGHT = 210;
const PAD = { top: 14, right: 12, bottom: 34, left: 34 };
const INNER_W = WIDTH - PAD.left - PAD.right;
const INNER_H = HEIGHT - PAD.top - PAD.bottom;

export default function GradeTrendChart({ points }: GradeTrendChartProps) {
  if (points.length === 0) {
    return (
      <section className="trendPanel">
        <h3 className="trendTitle">Grade trend</h3>
        <p className="small-text muted">
          A point appears here for each term once its grades are recorded.
        </p>
      </section>
    );
  }

  const cumulativePoints = points.filter((p) => p.cumulative_average !== null);
  const values = [
    ...points.map((p) => p.term_average),
    ...cumulativePoints.map((p) => p.cumulative_average as number),
  ];
  // Round the bounds out to whole steps so the axis labels are readable, and
  // keep a floor of 5 points of range so a steady record isn't drawn as noise.
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const min = Math.floor((rawMin - 2) / 5) * 5;
  const max = Math.ceil((rawMax + 2) / 5) * 5;
  const span = max - min || 1;

  const x = (index: number) =>
    PAD.left + (points.length === 1 ? INNER_W / 2 : (index / (points.length - 1)) * INNER_W);
  const y = (value: number) => PAD.top + (1 - (value - min) / span) * INNER_H;

  const termLine = points.map((p, i) => `${x(i)},${y(p.term_average)}`).join(" ");

  // Terms before any final grade exists have no cumulative to plot, so the
  // line starts where the data does rather than from zero.
  const cumulativeLine = points
    .map((p, i) => (p.cumulative_average === null ? null : `${x(i)},${y(p.cumulative_average)}`))
    .filter((entry): entry is string => entry !== null)
    .join(" ");

  const ticks = [min, min + span / 2, max];

  return (
    <section className="trendPanel">
      <div className="trendHeader">
        <h3 className="trendTitle">Grade trend</h3>
        <div className="trendLegend">
          <span className="trendKey trendKey--cumulative">Cumulative</span>
          <span className="trendKey trendKey--term">Per term</span>
        </div>
      </div>

      <div className="trendScroll">
        <svg
          className="trendChart"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`Grade trend across ${points.length} terms`}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                className="trendGrid"
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
              />
              <text className="trendAxis" x={PAD.left - 6} y={y(tick) + 3} textAnchor="end">
                {Math.round(tick)}
              </text>
            </g>
          ))}

          <polyline className="trendLine trendLine--term" points={termLine} />
          {cumulativeLine && (
            <polyline className="trendLine trendLine--cumulative" points={cumulativeLine} />
          )}

          {points.map((point, index) => (
            <g key={point.label}>
              <circle
                className="trendDot trendDot--term"
                cx={x(index)}
                cy={y(point.term_average)}
                r={2.5}
              />
              {point.cumulative_average !== null && (
                <circle
                  className="trendDot trendDot--cumulative"
                  cx={x(index)}
                  cy={y(point.cumulative_average)}
                  r={3}
                />
              )}
              <text
                className="trendAxis"
                x={x(index)}
                y={HEIGHT - PAD.bottom + 16}
                textAnchor="middle"
              >
                {point.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </section>
  );
}
