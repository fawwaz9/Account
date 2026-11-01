import { useEffect, useRef, useState } from "react";
import { fetchWhatIf } from "../api";
import { WhatIfIn, WhatIfOutcome, WhatIfPurchase, WhatIfResult } from "../types";
import { formatMoney } from "../money";

/** Whose plan. */
interface WhatIfPanelProps {
  readonly userId: string;
}

/** How long to wait after the last change before asking the server. */
const SETTLE_MS = 300;
const WIDTH = 560;
const HEIGHT = 190;
const PAD = { top: 14, right: 12, bottom: 26, left: 52 };

/** A date as "Dec 3". */
function shortDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Both curves on one scale, the plan dashed and the scenario solid. */
function Curves({ baseline, scenario }: { baseline: WhatIfOutcome; scenario: WhatIfOutcome }) {
  const all = [...baseline.points, ...scenario.points].map((p) => p.balance);
  const min = Math.min(0, ...all);
  const max = Math.max(0, ...all);
  const span = max - min || 1;
  const n = Math.max(baseline.points.length, 2);
  const x = (i: number) => PAD.left + (i / (n - 1)) * (WIDTH - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - min) / span) * (HEIGHT - PAD.top - PAD.bottom);
  const line = (o: WhatIfOutcome) => o.points.map((p, i) => `${x(i)},${y(p.balance)}`).join(" ");
  const first = baseline.points[0];
  const last = baseline.points[baseline.points.length - 1];

  return (
    <svg className="whatIfChart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img"
      aria-label={`Ending ${formatMoney(baseline.ending_balance)} as planned, ${formatMoney(scenario.ending_balance)} with the changes`}>
      {[max, (max + min) / 2, min].map((tick) => (
        <g key={tick}>
          <line className="whatIfGrid" x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} />
          <text className="whatIfAxis" x={PAD.left - 6} y={y(tick) + 3} textAnchor="end">
            {formatMoney(tick, { whole: true })}
          </text>
        </g>
      ))}
      {min < 0 && <line className="whatIfZero" x1={PAD.left} x2={WIDTH - PAD.right} y1={y(0)} y2={y(0)} />}
      <polyline className="whatIfBase" points={line(baseline)} />
      <polyline className="whatIfScenario" points={line(scenario)} />
      {first && <text className="whatIfAxis" x={PAD.left} y={HEIGHT - 8}>{shortDate(first.on_date)}</text>}
      {last && <text className="whatIfAxis" x={WIDTH - PAD.right} y={HEIGHT - 8} textAnchor="end">{shortDate(last.on_date)}</text>}
    </svg>
  );
}

/** A number field's value, or undefined when blank. */
function numberOrUndefined(value: string): number | undefined {
  return value.trim() === "" ? undefined : Number(value);
}

/**
 * The money what-if (Phase 4 item 14, §13.5): the year plan re-run with changed hours,
 * a stretch without shifts, a different wage, spending or one-off purchases. Money
 * only; nothing here touches grades. Nothing is saved.
 */
export default function WhatIfPanel({ userId }: WhatIfPanelProps) {
  const [hours, setHours] = useState("");
  const [rate, setRate] = useState("");
  const [spending, setSpending] = useState("");
  const [noFrom, setNoFrom] = useState("");
  const [noUntil, setNoUntil] = useState("");
  const [purchases, setPurchases] = useState<WhatIfPurchase[]>([]);
  const [draft, setDraft] = useState<WhatIfPurchase>({ label: "", amount: 0, on_date: "" });
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  useEffect(() => {
    const scenario: WhatIfIn = {
      hours_per_week: numberOrUndefined(hours) ?? 0,
      hourly_rate: numberOrUndefined(rate) ?? null,
      monthly_spending_change: numberOrUndefined(spending) ?? 0,
      no_shifts_from: noFrom && noUntil ? noFrom : null,
      no_shifts_until: noFrom && noUntil ? noUntil : null,
      purchases,
    };
    const ticket = ++latest.current;
    const timer = window.setTimeout(() => {
      fetchWhatIf(userId, scenario)
        .then((answer) => { if (ticket === latest.current) { setResult(answer); setError(null); } })
        .catch((err) => { if (ticket === latest.current) setError(err instanceof Error ? err.message : "Couldn't work that out."); });
    }, SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [userId, hours, rate, spending, noFrom, noUntil, purchases]);

  function addPurchase() {
    if (!draft.label.trim() || !(draft.amount > 0) || !draft.on_date || purchases.length >= 10) return;
    setPurchases([...purchases, { ...draft, label: draft.label.trim() }]);
    setDraft({ label: "", amount: 0, on_date: "" });
  }

  function examSeason() {
    if (!result?.exam_season) return;
    setNoFrom(result.exam_season.starts_on);
    setNoUntil(result.exam_season.ends_on);
  }

  const diff = result?.difference ?? 0;

  return (
    <details className="whatIf">
      <summary>What if…</summary>
      <p className="small-text muted">Change anything below; the plan above doesn't move. Nothing is saved.</p>

      <div className="whatIfInputs">
        <label>
          <span className="small-text muted">Hours a week more (or less, with a minus)</span>
          <input className="whatIfInput" type="number" min={-40} max={40} step={0.5} value={hours}
            onChange={(e) => setHours(e.target.value)} placeholder="0" aria-label="Hours a week more or less" />
        </label>
        <label>
          <span className="small-text muted">Hourly rate instead</span>
          <input className="whatIfInput" type="number" min={0} max={200} step={0.25} value={rate}
            onChange={(e) => setRate(e.target.value)} placeholder="as now" aria-label="A different hourly rate" />
        </label>
        <label>
          <span className="small-text muted">Spending a month more (or less, with a minus)</span>
          <input className="whatIfInput" type="number" min={-10000} max={10000} step={10} value={spending}
            onChange={(e) => setSpending(e.target.value)} placeholder="0" aria-label="Spending a month more or less" />
        </label>
        <fieldset className="whatIfNoShifts">
          <legend className="small-text muted">No shifts at all</legend>
          <input className="whatIfInput" type="date" value={noFrom} onChange={(e) => setNoFrom(e.target.value)}
            aria-label="No shifts from" />
          <span className="small-text muted">to</span>
          <input className="whatIfInput" type="date" value={noUntil} onChange={(e) => setNoUntil(e.target.value)}
            aria-label="No shifts until" />
          {result?.exam_season && (
            <button type="button" className="whatIfPreset" onClick={examSeason}>
              Exam season ({shortDate(result.exam_season.starts_on)}–{shortDate(result.exam_season.ends_on)})
            </button>
          )}
        </fieldset>
        <fieldset className="whatIfPurchase">
          <legend className="small-text muted">A one-off purchase</legend>
          <input className="whatIfInput" type="text" maxLength={60} value={draft.label} placeholder="laptop"
            onChange={(e) => setDraft({ ...draft, label: e.target.value })} aria-label="What it is" />
          <input className="whatIfInput" type="number" min={0} max={100000} step={1} value={draft.amount || ""}
            placeholder="800" onChange={(e) => setDraft({ ...draft, amount: Number(e.target.value) })} aria-label="How much" />
          <input className="whatIfInput" type="date" value={draft.on_date}
            onChange={(e) => setDraft({ ...draft, on_date: e.target.value })} aria-label="When" />
          <button type="button" className="whatIfPreset" onClick={addPurchase}>Add</button>
        </fieldset>
        {purchases.length > 0 && (
          <ul className="whatIfPurchases small-text">
            {purchases.map((p, i) => (
              <li key={`${p.label}-${i}`}>
                {p.label} · {formatMoney(p.amount)} · {shortDate(p.on_date)}{" "}
                <button type="button" className="whatIfRemove" aria-label={`Remove ${p.label}`}
                  onClick={() => setPurchases(purchases.filter((_, j) => j !== i))}>×</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && <p className="small-text error" role="alert">{error}</p>}

      {result && (
        <div className="whatIfResult" aria-live="polite">
          <p className="whatIfHeadline">
            {diff === 0 ? "No change by " : <>{diff > 0 ? "+" : "−"}{formatMoney(Math.abs(diff))} by </>}
            {shortDate(result.ends_on)}
            <span className="muted small-text">
              {" "}· {formatMoney(result.scenario.ending_balance)} against {formatMoney(result.baseline.ending_balance)} as planned
            </span>
          </p>
          <p className="small-text">
            Lowest {formatMoney(result.scenario.lowest_balance)} on {shortDate(result.scenario.lowest_on)}
            {result.scenario.negative_on
              ? <span className="whatIfNegative"> · below zero from {shortDate(result.scenario.negative_on)}</span>
              : " · never below zero"}
          </p>
          <div className="whatIfLegend small-text">
            <span className="whatIfKeyBase">as planned</span>
            <span className="whatIfKeyScenario">with the changes</span>
          </div>
          <div className="whatIfChartWrap"><Curves baseline={result.baseline} scenario={result.scenario} /></div>
          {result.capped.length > 0 && (
            <ul className="whatIfCapped small-text">{result.capped.map((c) => <li key={c}>{c}</li>)}</ul>
          )}
          <details className="forecastAssumptions">
            <summary className="small-text muted">What this assumes</summary>
            <ul>{result.assumptions.map((a) => <li key={a} className="small-text">{a}</li>)}</ul>
          </details>
        </div>
      )}
    </details>
  );
}
