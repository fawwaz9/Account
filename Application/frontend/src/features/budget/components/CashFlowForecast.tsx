import { useEffect, useRef, useState } from "react";
import { fetchForecast } from "../api";
import { CashFlowForecast as Forecast, ForecastPoint } from "../types";
import { formatMoney } from "../money";
import { useAuth } from "../../../app/auth/AuthContext";

/** Props for the forecast panel. */
interface CashFlowForecastProps {
  /** Bumped by the page when something changes, to refetch. */
  readonly nonce: number;
}

/**
 * Forecast panel: the day spending hits $0, or the lowest point, with runway and run rates.
 * All projections, assumptions one click away; renders nothing when empty or failed.
 */
export default function CashFlowForecast({ nonce }: CashFlowForecastProps) {
  const { user } = useAuth();
  const userId = user?.id;
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    if (!userId) return;
    const ticket = ++latestRequest.current;
    let cancelled = false;

    fetchForecast(userId)
      .then((result) => {
        if (!cancelled && ticket === latestRequest.current) setForecast(result);
      })
      .catch(() => {
        if (!cancelled && ticket === latestRequest.current) setForecast(null);
      });

    return () => { cancelled = true; };
  }, [userId, nonce]);

  if (!forecast || isEmpty(forecast)) return null;

  const end = shortDate(forecast.ends_on);
  const below = forecast.negative_on;

  return (
    <section className={`forecastBlock${below ? " forecastBlockOver" : ""}`} aria-label="Where this is heading">
      <div className="forecastHead">
        <h2>Where this is heading</h2>
        <span className="small-text muted">
          to {end}{forecast.ends_at_term_end ? ", the end of term" : ""}
        </span>
      </div>

      <p className="forecastHeadline">
        {below ? (
          <>
            At this pace your spending accounts go below $0 on <strong>{shortDate(below)}</strong>
            {" "}({weeksFrom(forecast.starts_on, below)}).
          </>
        ) : (
          <>
            Your spending accounts stay above $0 to {end}. Lowest:{" "}
            <strong>{formatMoney(forecast.lowest_balance)}</strong> on {shortDate(forecast.lowest_on)}.
          </>
        )}
      </p>

      <Sparkline points={forecast.points} negativeOn={below} />

      {forecast.runway && (
        <p className="small-text forecastLine">
          {forecast.runway.lasts_until ? (
            <>
              Runway: {formatMoney(forecast.runway.liquid)} in spending and savings lasts until{" "}
              <strong>{shortDate(forecast.runway.lasts_until)}</strong> at your recent pace of{" "}
              {formatMoney(forecast.runway.daily_burn)} a day.
            </>
          ) : (
            <>Over the last {forecast.spending_history_days} days, money in has kept up with money out.</>
          )}
        </p>
      )}

      {forecast.run_rates.length > 0 && (
        <div className="forecastRunRates">
          <span className="small-text muted">One-off spending at its current pace, to {end}</span>
          <ul>
            {forecast.run_rates.slice(0, 3).map((rate) => (
              <li key={rate.merchant}>
                <span className="small-text">{rate.merchant}</span>
                <span className="small-text">{formatMoney(rate.projected)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="forecastAssumptions">
        <summary className="small-text muted">How this is worked out</summary>
        <ul>
          {forecast.assumptions.map((line) => (
            <li key={line} className="small-text">{line}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}

/** No money, no history and nothing scheduled: nothing worth forecasting. */
function isEmpty(forecast: Forecast): boolean {
  return forecast.starting_balance === 0
    && forecast.spending_history_days === 0
    && forecast.events.length === 0;
}

/** "Mar 3" from a YYYY-MM-DD string, in the browser's locale. */
function shortDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** How far off a date is, in words: tomorrow, in N days, or in N weeks. */
function weeksFrom(start: string, end: string): string {
  const days = Math.round(
    (new Date(`${end}T00:00:00`).getTime() - new Date(`${start}T00:00:00`).getTime()) / 86_400_000,
  );
  if (days < 7) return days <= 1 ? "tomorrow" : `in ${days} days`;
  const weeks = Math.round(days / 7);
  return `in ${weeks} ${weeks === 1 ? "week" : "weeks"}`;
}

/** Sparkline width, in viewBox units. */
const WIDTH = 300;
/** Sparkline height, in viewBox units. */
const HEIGHT = 56;

/** The projected balance curve, with $0 drawn whenever the curve reaches it. */
function Sparkline({
  points,
  negativeOn,
}: {
  readonly points: ForecastPoint[];
  readonly negativeOn: string | null;
}) {
  if (points.length < 2) return null;
  const values = points.map((point) => point.balance);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const span = high - low || 1;
  const x = (index: number) => (index / (points.length - 1)) * WIDTH;
  const y = (value: number) => HEIGHT - ((value - low) / span) * HEIGHT;
  const line = points.map((point, index) => `${x(index).toFixed(1)},${y(point.balance).toFixed(1)}`).join(" ");
  const crossing = negativeOn ? points.findIndex((point) => point.on_date === negativeOn) : -1;

  return (
    <svg
      className="forecastSparkline"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`Balance from ${formatMoney(values[0])} to ${formatMoney(values[values.length - 1])}`}
    >
      {low < 0 && (
        <line className="forecastZero" x1={0} x2={WIDTH} y1={y(0)} y2={y(0)} />
      )}
      <polyline className="forecastCurve" points={line} />
      {crossing >= 0 && (
        <circle className="forecastCross" cx={x(crossing)} cy={y(0)} r={3} />
      )}
    </svg>
  );
}
