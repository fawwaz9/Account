import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { acceptWeekPlan, fetchWeekPlan, PlannedBlock, WeekPlan } from "../plannerApi";
import { clockTime, dueLabel, duration } from "../../../shared/utils/dateUtils";

/** Whose week, and what to do once blocks are on the calendar. */
interface PlannerModalProps {
  readonly userId: string;
  readonly onClose: () => void;
  readonly onAccepted?: (created: number) => void;
}

/** A block's identity in the list: one task can hold several blocks. */
function key(b: PlannedBlock): string {
  return `${b.task_id}-${b.on_date}-${b.starts_at}`;
}

/** "Mon 2 Nov" for a day heading. */
function dayHeading(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

/**
 * The weekly planner (Phase 4 item 2): each open task's work placed in free time before
 * it's due, with why, ticked by default; "Add to calendar" writes the ticked ones as the
 * planner's events (D7). What didn't fit is said, not squeezed in.
 */
export default function PlannerModal({ userId, onClose, onAccepted }: PlannerModalProps) {
  const [plan, setPlan] = useState<WeekPlan | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWeekPlan(userId)
      .then((next) => {
        if (cancelled) return;
        setPlan(next);
        setChosen(new Set(next.blocks.map(key)));
      })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "Couldn't plan the week."); });
    return () => { cancelled = true; };
  }, [userId]);

  function toggle(b: PlannedBlock) {
    setChosen((was) => {
      const next = new Set(was);
      if (next.has(key(b))) next.delete(key(b)); else next.add(key(b));
      return next;
    });
  }

  async function add() {
    if (!plan) return;
    const picked = plan.blocks.filter((b) => chosen.has(key(b)));
    if (picked.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const { created } = await acceptWeekPlan(userId, picked);
      setDone(created);
      onAccepted?.(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't add those.");
    } finally {
      setBusy(false);
    }
  }

  const days = plan ? [...new Set(plan.blocks.map((b) => b.on_date))] : [];

  return (
    <Modal title="Plan my week" onClose={onClose} panelClassName="plannerPanel">
      {!plan && !error && <p className="muted small-text">Working it out…</p>}
      {error && <p className="error">{error}</p>}

      {done !== null ? (
        <p className="plannerDone">{done} block{done === 1 ? "" : "s"} added to your calendar.</p>
      ) : plan && (
        <>
          {plan.blocks.length === 0 && plan.unplaced.length === 0 && (
            <p className="small-text muted">Nothing due in the next week needs planning.</p>
          )}
          {days.map((day) => (
            <section key={day} className="plannerDay">
              <h3 className="plannerDayTitle">{dayHeading(day)}</h3>
              <ul className="plannerBlocks">
                {plan.blocks.filter((b) => b.on_date === day).map((b) => (
                  <li key={key(b)} className="plannerBlock">
                    <label>
                      <input type="checkbox" checked={chosen.has(key(b))} onChange={() => toggle(b)}
                        aria-label={`Add ${b.title}, ${clockTime(b.starts_at)} to ${clockTime(b.ends_at)}`} />
                      <span className="plannerTime">{clockTime(b.starts_at)}–{clockTime(b.ends_at)}</span>
                      <span className="plannerWhat">
                        {b.title}{b.course_code ? <span className="muted small-text"> · {b.course_code}</span> : null}
                        <span className="plannerWhy small-text muted">{b.reason}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          ))}

          {plan.unplaced.length > 0 && (
            <section className="plannerMissed" aria-label="Didn't fit">
              <h3 className="plannerDayTitle">Didn&apos;t fit</h3>
              <ul className="plannerBlocks">
                {plan.unplaced.map((u) => (
                  <li key={u.task_id} className="small-text">
                    <strong>{u.title}</strong>, due {dueLabel(u.due_date).toLowerCase()}: {u.reason}{" "}
                    <span className="muted">({duration(u.minutes_short)} short)</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <details className="forecastAssumptions">
            <summary className="small-text muted">How this is worked out</summary>
            <ul>{plan.assumptions.map((a) => <li key={a} className="small-text">{a}</li>)}</ul>
          </details>
        </>
      )}

      <div className="flex justify-end gap-3 pt-4">
        {done === null && plan && plan.blocks.length > 0 && (
          <button type="button" className="buttons" onClick={() => void add()} disabled={busy || chosen.size === 0}>
            {busy ? "Adding…" : `Add ${chosen.size} to calendar`}
          </button>
        )}
        <button type="button" onClick={onClose} className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200">
          {done === null ? "Close" : "Done"}
        </button>
      </div>
    </Modal>
  );
}
