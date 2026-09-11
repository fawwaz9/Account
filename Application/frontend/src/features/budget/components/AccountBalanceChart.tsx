import { BalancePoint } from "../types";
import { formatMoney } from "../money";

interface AccountBalanceChartProps {
  readonly points: readonly BalancePoint[];
}

const WIDTH = 560;
const HEIGHT = 180;
const PAD = { top: 16, right: 12, bottom: 30, left: 46 };
const INNER_W = WIDTH - PAD.left - PAD.right;
const INNER_H = HEIGHT - PAD.top - PAD.bottom;

/**
 * The account's whole history, not the selected month.
 *
 * Kept as its own figure rather than laid over the daily bars: a balance in the
 * tens of thousands and a day's flow in the hundreds share no sensible scale,
 * and two y-axes on one chart is the surest way to make both unreadable.
 */
export default function AccountBalanceChart({ points }: AccountBalanceChartProps) {
  if (points.length === 0) {
    return (
      <section className="flowPanel">
        <h3 className="flowTitle">Balance over time</h3>
        <p className="small-text muted">
          The line starts as soon as this account has its first movement.
        </p>
      </section>
    );
  }

  const values = points.map((point) => point.balance);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);

  // Unlike the bars, this line is deliberately allowed to float. A balance
  // sitting between 12,000 and 12,400 all year is a flat line if the axis is
  // forced to zero, and the whole point of the chart is the shape of the
  // change. Zero is pulled in only when the account actually goes negative.
  const padding = (rawMax - rawMin || Math.abs(rawMax) || 1) * 0.08;
  const min = rawMin < 0 ? Math.min(rawMin - padding, 0) : rawMin - padding;
  const max = rawMax + padding;
  const span = max - min || 1;

  const x = (index: number) =>
    PAD.left + (points.length === 1 ? INNER_W / 2 : (index / (points.length - 1)) * INNER_W);
  const y = (value: number) => PAD.top + (1 - (value - min) / span) * INNER_H;

  const line = points.map((point, index) => `${x(index)},${y(point.balance)}`).join(" ");
  const ticks = [max, min + span / 2, min];

  return (
    <section className="flowPanel">
      <div className="flowHeader">
        <h3 className="flowTitle">Balance over time</h3>
        <span className="small-text muted">All history</span>
      </div>

      <div className="flowScroll">
        <svg
          className="flowChart"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`Balance across ${points.length} days with movement`}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                className="flowGrid"
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
              />
              <text className="flowAxis" x={PAD.left - 6} y={y(tick) + 3} textAnchor="end">
                {formatMoney(tick, { compact: true })}
              </text>
            </g>
          ))}

          {min < 0 && (
            <line
              className="flowZero"
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(0)}
              y2={y(0)}
            />
          )}

          <polyline className="flowLine" points={line} />

          {points.map((point, index) => (
            <g key={point.day}>
              <title>{`${point.day} · ${formatMoney(point.balance)}`}</title>
              <circle className="flowDot" cx={x(index)} cy={y(point.balance)} r={2.5} />
            </g>
          ))}

          <text className="flowAxis" x={PAD.left} y={HEIGHT - PAD.bottom + 15} textAnchor="start">
            {points[0].day}
          </text>
          {points.length > 1 && (
            <text
              className="flowAxis"
              x={WIDTH - PAD.right}
              y={HEIGHT - PAD.bottom + 15}
              textAnchor="end"
            >
              {points[points.length - 1].day}
            </text>
          )}
        </svg>
      </div>
    </section>
  );
}
