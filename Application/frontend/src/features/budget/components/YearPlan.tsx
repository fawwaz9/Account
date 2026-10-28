import { FormEvent, useEffect, useRef, useState } from "react";
import { fetchPlan } from "../api";
import { AnnualPlan, PlanGoal } from "../types";
import { formatMoney } from "../money";
import { useAuth } from "../../../app/auth/AuthContext";
import PlanVsActual from "./PlanVsActual";

/** Props for the year plan. */
interface YearPlanProps {
  /** Bumped by the page when something changes, to refetch. */
  readonly nonce: number;
}

/**
 * The year as one running liquid balance by month, and the extra weekly hours a target takes.
 * A reload drops any target answer and shows the plan alone.
 */
export default function YearPlan({ nonce }: YearPlanProps) {
  const { user } = useAuth();
  const userId = user?.id;
  const [planned, setPlanned] = useState<AnnualPlan | null>(null);
  const [target, setTarget] = useState("");
  const [until, setUntil] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asked, setAsked] = useState(false);
  const latestRequest = useRef(0);

  useEffect(() => {
    if (!userId) return;
    const ticket = ++latestRequest.current;
    let cancelled = false;
    setAsked(false);

    fetchPlan(userId)
      .then((result) => {
        if (!cancelled && ticket === latestRequest.current) setPlanned(result);
      })
      .catch(() => {
        if (!cancelled && ticket === latestRequest.current) setPlanned(null);
      });

    return () => { cancelled = true; };
  }, [userId, nonce]);

  async function solve(event: FormEvent) {
    event.preventDefault();
    if (!userId) return;
    const ticket = ++latestRequest.current;
    setWorking(true);
    setError(null);
    try {
      const result = await fetchPlan(userId, Number(target), until || undefined);
      if (ticket !== latestRequest.current) return;
      setPlanned(result);
      setAsked(true);
    } catch (err) {
      if (ticket === latestRequest.current) {
        setError(err instanceof Error && err.message ? err.message : "Couldn't work that out.");
      }
    } finally {
      if (ticket === latestRequest.current) setWorking(false);
    }
  }

  if (!planned || isEmpty(planned)) return null;

  return (
    <section className="yearPlan" aria-label="The year, month by month">
      <div className="forecastHead">
        <h2>The year, month by month</h2>
        <span className="small-text muted">
          spending, savings and emergency, to {longDate(planned.ends_on)}
        </span>
      </div>

      <div className="yearPlanTable">
        <table>
          <thead>
            <tr>
              <th scope="col">Month</th>
              <th scope="col">In</th>
              <th scope="col">Out</th>
              <th scope="col">Balance</th>
            </tr>
          </thead>
          <tbody>
            {planned.months.map((row) => (
              <tr key={row.month}>
                <th scope="row">{monthName(row.month)}</th>
                <td>{row.money_in ? formatMoney(row.money_in) : ""}</td>
                <td>{row.money_out ? formatMoney(row.money_out) : ""}</td>
                <td className={row.end_balance < 0 ? "yearPlanNegative" : undefined}>
                  {formatMoney(row.end_balance)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form className="yearPlanGoal" onSubmit={solve}>
        <label>
          <span className="small-text muted">Reach</span>
          <input
            className="--input"
            type="number"
            min={0}
            step="1"
            inputMode="decimal"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            placeholder="2000"
            aria-label="Balance to reach"
            required
          />
        </label>
        <label>
          <span className="small-text muted">by</span>
          <input
            className="--input"
            type="date"
            value={until}
            onChange={(event) => setUntil(event.target.value)}
            aria-label="Reach it by"
          />
        </label>
        <button type="submit" className="buttons" disabled={working}>
          {working ? "Working…" : "Work it out"}
        </button>
      </form>

      {error && <p className="small-text error" role="alert">{error}</p>}
      {asked && <GoalAnswer goal={planned.goal} endsOn={planned.ends_on} />}

      {/* Under the plan it saves: the plan is recomputed on every read, so
          only a saved copy can be compared with what happened. */}
      {userId && <PlanVsActual userId={userId} nonce={nonce} />}

      <details className="forecastAssumptions">
        <summary className="small-text muted">How this is worked out</summary>
        <ul>
          {planned.assumptions.map((line) => (
            <li key={line} className="small-text">{line}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}

/** The hours-to-goal answer: hours a week with scenarios, already on track, or no hourly job. */
function GoalAnswer({ goal, endsOn }: { readonly goal: PlanGoal | null; readonly endsOn: string }) {
  if (!goal) {
    return (
      <p className="small-text yearPlanAnswer" role="status">
        Extra hours can't be priced without an hourly job that has a rate. Add one in Jobs.
      </p>
    );
  }
  const by = longDate(goal.target_on ?? endsOn);
  if (goal.extra_hours_per_week === null) {
    return (
      <p className="small-text yearPlanAnswer" role="status">
        Already on track: the plan reaches {formatMoney(goal.base_end_balance)} by {by}, without
        extra hours.
      </p>
    );
  }
  return (
    <div className="yearPlanAnswer" role="status">
      <p className="small-text">
        <strong>{goal.extra_hours_per_week} extra hours a week</strong> at {goal.job_name} reaches{" "}
        {formatMoney(goal.target)} by {by}. Each hour adds {formatMoney(goal.net_hourly)}.
      </p>
      <ul className="yearPlanScenarios">
        {goal.scenarios.map((scenario) => (
          <li key={scenario.extra_hours_per_week}>
            <span className="small-text">
              {scenario.extra_hours_per_week === 0 ? "No extra hours" : `+${scenario.extra_hours_per_week} h a week`}
            </span>
            <span className={`small-text${scenario.end_balance < 0 ? " yearPlanNegative" : ""}`}>
              {formatMoney(scenario.end_balance)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Nothing held and nothing moving: rows of $0.00 say nothing. */
function isEmpty(planned: AnnualPlan): boolean {
  return planned.starting_balance === 0
    && planned.months.every((row) => row.money_in === 0 && row.money_out === 0);
}

/** "Sep 2026" from a YYYY-MM-DD string, in the browser's locale. */
function monthName(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

/** "Apr 30, 2027" from a YYYY-MM-DD string, in the browser's locale. */
function longDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}
