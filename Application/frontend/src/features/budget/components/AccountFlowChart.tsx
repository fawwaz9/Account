import { DayFlow } from "../types";
import { formatMoney } from "../money";

/** Props: one zero-filled entry per day of the month, and the month's name. */
interface AccountFlowChartProps {
  readonly days: readonly DayFlow[];
  readonly monthLabel: string;
}

/** Chart width in viewBox units; hand-drawn SVG, and the wrapper scrolls on narrow screens. */
const WIDTH = 560;
/** Chart height, in viewBox units. */
const HEIGHT = 220;
/** Space around the plot for the axes. */
const PAD = { top: 16, right: 12, bottom: 32, left: 46 };
/** Plot width inside the padding. */
const INNER_W = WIDTH - PAD.left - PAD.right;
/** Plot height inside the padding. */
const INNER_H = HEIGHT - PAD.top - PAD.bottom;

/** Daily money in and out across a month, two bars per day from a zero baseline. */
export default function AccountFlowChart({ days, monthLabel }: AccountFlowChartProps) {
  const peak = days.reduce((most, day) => Math.max(most, day.money_in, day.money_out), 0);

  // The guard is on the peak, not on the length: the server zero-fills every
  // day of the month, so this array is never empty. A zero peak would divide
  // through to NaN and render an invisible, silently broken chart.
  if (days.length === 0 || peak === 0) {
    return (
      <section className="flowPanel">
        <h3 className="flowTitle">Money in and out</h3>
        <p className="small-text muted">Nothing moved in {monthLabel}.</p>
      </section>
    );
  }

  const top = niceCeiling(peak);
  const slot = INNER_W / days.length;
  // Two bars to a day with a hairline between them, so a slot reads as one day.
  const barW = Math.max(3, Math.min(9, slot / 2 - 1));
  const baseline = PAD.top + INNER_H;

  // Bars encode magnitude, so the baseline is zero and never floats.
  const y = (value: number) => baseline - (value / top) * INNER_H;
  const slotX = (index: number) => PAD.left + slot * index;

  const ticks = [top, top / 2, 0];

  return (
    <section className="flowPanel">
      <div className="flowHeader">
        <h3 className="flowTitle">Money in and out</h3>
        <div className="flowLegend">
          <span className="flowKey flowKey--in">In</span>
          <span className="flowKey flowKey--out">Out</span>
        </div>
      </div>

      <div className="flowScroll">
        <svg
          className="flowChart"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`Daily money in and out across ${monthLabel}`}
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

          {days.map((day, index) => {
            const dayOfMonth = Number(day.day.slice(8));
            const centre = slotX(index) + slot / 2;

            return (
              <g key={day.day}>
                {/* A native title is a free tooltip and is read aloud, which
                    matters because only every fifth day is labelled. */}
                <title>
                  {`${day.day} · in ${formatMoney(day.money_in)} · out ${formatMoney(day.money_out)}`}
                </title>

                {day.money_in > 0 && (
                  <rect
                    className="flowBar flowBar--in"
                    x={centre - barW - 1}
                    y={y(day.money_in)}
                    width={barW}
                    height={baseline - y(day.money_in)}
                    rx={2}
                  />
                )}

                {day.money_out > 0 && (
                  <rect
                    className="flowBar flowBar--out"
                    x={centre + 1}
                    y={y(day.money_out)}
                    width={barW}
                    height={baseline - y(day.money_out)}
                    rx={2}
                  />
                )}

                {showLabel(dayOfMonth, days.length) && (
                  <text
                    className="flowAxis"
                    x={centre}
                    y={HEIGHT - PAD.bottom + 15}
                    textAnchor="middle"
                  >
                    {dayOfMonth}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </section>
  );
}

/** Label every fifth day and the last; a fifth-day label too close to the last is dropped. */
function showLabel(dayOfMonth: number, total: number) {
  if (dayOfMonth === total) return true;
  if (dayOfMonth % 5 !== 0) return false;
  return total - dayOfMonth >= 2;
}

/** Round an axis top up to 1, 2, 2.5, 5 or 10 times a power of ten. */
function niceCeiling(value: number) {
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const steps = [1, 2, 2.5, 5, 10];
  const step = steps.find((candidate) => value <= candidate * magnitude) ?? 10;
  return step * magnitude;
}
