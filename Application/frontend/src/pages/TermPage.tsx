import { useEffect, useRef, useState } from "react";
import { useAuth } from "../app/auth/AuthContext";
import HelpTip from "../shared/components/HelpTip";
import { fetchTermDefaults, simulateTerm, TermIn, TermResult } from "../features/insights/api";
import { formatMoney } from "../features/budget/money";
import "../styles/term.css";

/** How long to wait after the last slider move before asking the server. */
const SETTLE_MS = 250;

/** One slider with its label and value. */
function Slider({ label, value, min, max, step, unit, onChange, disabled = false }: {
  readonly label: string; readonly value: number; readonly min: number; readonly max: number;
  readonly step: number; readonly unit: string; readonly onChange: (v: number) => void; readonly disabled?: boolean;
}) {
  return (
    <label className={disabled ? "termSimSlider termSimSliderOff" : "termSimSlider"}>
      <span className="termSimSliderLabel">{label}</span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))} aria-label={label} />
      <span className="termSimSliderValue">{value}{unit}</span>
    </label>
  );
}

/**
 * The term simulator (Phase 4 item 9, §13.19): the three rooms over one 168-hour week.
 * Work hours move time and money only; nothing academic shows until study hours are set
 * directly, and then only what they cover, beside each course's band as it stands.
 */
export default function TermPage() {
  const { user } = useAuth();
  const userId = user?.id;
  const [week, setWeek] = useState<TermIn | null>(null);
  const [studySet, setStudySet] = useState(false);
  const [estimate, setEstimate] = useState(0);
  const [result, setResult] = useState<TermResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  useEffect(() => {
    if (!userId) return;
    fetchTermDefaults(userId)
      .then((d) => {
        setEstimate(d.study_hours);
        setWeek({ sleep_hours: d.sleep_hours, class_hours: d.class_hours, study_hours: null, work_hours: d.work_hours,
          workouts_per_week: d.workouts_per_week, workout_minutes: d.workout_minutes,
          overhead_hours: d.overhead_hours, monthly_spending_change: 0 });
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't read your figures."));
  }, [userId]);

  useEffect(() => {
    if (!userId || !week) return;
    const ticket = ++latest.current;
    const timer = window.setTimeout(() => {
      simulateTerm(userId, week)
        .then((answer) => { if (ticket === latest.current) { setResult(answer); setError(null); } })
        .catch((err) => { if (ticket === latest.current) setError(err instanceof Error ? err.message : "Couldn't work that out."); });
    }, SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [userId, week]);

  function set<K extends keyof TermIn>(key: K, value: TermIn[K]) {
    setWeek((was) => (was ? { ...was, [key]: value } : was));
  }

  function toggleStudy(on: boolean) {
    setStudySet(on);
    set("study_hours", on ? Math.round(estimate) : null);
  }

  return (
    <div className="container termSimPage">
      <h1 className="title">
        Plan the term{" "}
        <HelpTip label="How the term simulator works">
          One week of the term, across your rooms. Classes, study and work start from your next four weeks;
          workouts from what you&apos;ve logged lately. Work hours change your time and money, never anything about
          your grades. Nothing is saved.
        </HelpTip>
      </h1>

      {error && <p className="error">{error}</p>}

      {week && (
        <div className="termSimLayout">
          <section className="termSimSliders" aria-label="Your week">
            <Slider label="Sleep a night" value={week.sleep_hours} min={4} max={12} step={0.5} unit="h"
              onChange={(v) => set("sleep_hours", v)} />
            <Slider label="Classes a week" value={week.class_hours} min={0} max={60} step={0.5} unit="h"
              onChange={(v) => set("class_hours", v)} />
            <label className="termSimCheck">
              <input type="checkbox" checked={studySet} onChange={(e) => toggleStudy(e.target.checked)} />
              Set my study hours
            </label>
            <Slider label="Study a week" value={week.study_hours ?? estimate} min={0} max={80} step={0.5} unit="h"
              onChange={(v) => set("study_hours", v)} disabled={!studySet} />
            <Slider label="Work a week" value={week.work_hours ?? 0} min={0} max={60} step={0.5} unit="h"
              onChange={(v) => set("work_hours", v)} />
            <Slider label="Workouts a week" value={week.workouts_per_week} min={0} max={14} step={1} unit=""
              onChange={(v) => set("workouts_per_week", v)} />
            <Slider label="Minutes each" value={week.workout_minutes} min={10} max={240} step={5} unit="m"
              onChange={(v) => set("workout_minutes", v)} />
            <Slider label="Everything else a day" value={week.overhead_hours} min={0} max={12} step={0.5} unit="h"
              onChange={(v) => set("overhead_hours", v)} />
            <Slider label="Spending a month" value={week.monthly_spending_change} min={-1000} max={1000} step={25}
              unit="" onChange={(v) => set("monthly_spending_change", v)} />
          </section>

          {result && (
            <section className="termSimResult" aria-live="polite">
              <div className="termSimCard">
                <h2 className="termSimHeading">
                  {result.time.fits
                    ? `Fits, with ${result.time.spare} hours spare`
                    : `Needs ${result.time.total} of your 168 hours: ${result.time.short_by} short`}
                </h2>
                <div className="termSimBar" role="img"
                  aria-label={result.time.rooms.map((r) => `${r.label} ${r.hours} hours`).join(", ")}>
                  {result.time.rooms.map((r) => (
                    <span key={r.room} className={`termSimBarPart termSimRoom-${r.room}`}
                      style={{ width: `${(r.hours / Math.max(168, result.time.total)) * 100}%` }} />
                  ))}
                </div>
                <ul className="termSimRooms small-text">
                  {result.time.rooms.map((r) => (
                    <li key={r.room}><span className={`termSimKey termSimRoom-${r.room}`} />{r.label} <strong>{r.hours}h</strong></li>
                  ))}
                </ul>
              </div>

              {result.money && (
                <div className="termSimCard">
                  <h2 className="termSimHeading">Money</h2>
                  <p className="small-text">
                    {result.money.difference === 0 ? "Ends where your plan does: " : `${result.money.difference > 0 ? "+" : "−"}${formatMoney(Math.abs(result.money.difference))} by the plan's end: `}
                    {formatMoney(result.money.scenario_ending)}
                    {result.money.negative_on
                      ? <span className="termSimWarn"> · below zero from {result.money.negative_on}</span>
                      : `, lowest ${formatMoney(result.money.lowest)}`}
                  </p>
                  {result.money.notes.map((n) => <p key={n} className="small-text termSimWarn">{n}</p>)}
                </div>
              )}

              <div className="termSimCard">
                <h2 className="termSimHeading">Exertion</h2>
                <p className="small-text">
                  About {result.body.points_per_week} points a week
                  {result.body.goal !== null && (result.body.meets_goal
                    ? `, reaching your goal of ${result.body.goal}`
                    : `, ${result.body.goal - result.body.points_per_week} short of your goal of ${result.body.goal}`)}
                </p>
              </div>

              {result.academic && (
                <div className="termSimCard">
                  <h2 className="termSimHeading">Study</h2>
                  <p className="small-text">{result.academic.reading}</p>
                  {result.academic.bands.length > 0 && (
                    <>
                      <p className="small-text muted">Where each course can still finish, as it stands:</p>
                      <ul className="termSimBands small-text">
                        {result.academic.bands.map((b) => (
                          <li key={b.code}>{b.code}: {b.worst}–{b.best}, now {b.current}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              )}

              <details className="termSimAssumptions">
                <summary className="small-text muted">What this assumes</summary>
                <ul>{result.assumptions.map((a) => <li key={a} className="small-text">{a}</li>)}</ul>
              </details>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
