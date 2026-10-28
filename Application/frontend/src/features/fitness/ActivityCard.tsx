import { FormEvent, useEffect, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import { shortDate, today } from "../../shared/utils/dateUtils";
import { ActivityKind, deleteActivity, Exertion, fetchExertion, logActivity, setExertionGoal } from "./api";

/** Activity kinds as offered, in the order people reach for them. */
const KINDS: { value: ActivityKind; label: string }[] = [
  { value: "run", label: "Run" }, { value: "walk", label: "Walk" }, { value: "cycle", label: "Cycle" },
  { value: "gym", label: "Gym" }, { value: "swim", label: "Swim" }, { value: "sport", label: "Sport" },
  { value: "hike", label: "Hike" }, { value: "yoga", label: "Yoga" }, { value: "other", label: "Other" },
];

/** A kind's label, for the list. */
const LABEL = Object.fromEntries(KINDS.map((k) => [k.value, k.label])) as Record<ActivityKind, string>;

/**
 * "Activity" (Phase 3 items 6-7): log what you did, see this week's points against your goal,
 * and a suggested goal beside it, advice you can take or leave.
 */
export default function ActivityCard({ userId }: { readonly userId: string }) {
  const [data, setData] = useState<Exertion | null>(null);
  const [kind, setKind] = useState<ActivityKind>("run");
  const [minutes, setMinutes] = useState("30");
  const [onDate, setOnDate] = useState(today());
  const [note, setNote] = useState("");
  const [goal, setGoal] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function show(next: Exertion) {
    setData(next);
    setGoal(next.goal === null ? "" : String(next.goal));
  }

  async function reload() {
    show(await fetchExertion(userId));
  }

  useEffect(() => {
    let cancelled = false;
    fetchExertion(userId)
      .then((found) => { if (!cancelled) show(found); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [userId]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save that");
    } finally {
      setBusy(false);
    }
  }

  function log(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      await logActivity(userId, { on_date: onDate, kind, minutes: Number(minutes), note: note.trim() || null });
      setNote("");
      await reload();
    });
  }

  function saveGoal(value: number | null) {
    void run(async () => show(await setExertionGoal(userId, value)));
  }

  async function remove(activityId: string) {
    await run(async () => {
      await deleteActivity(userId, activityId);
      setConfirming(null);
      await reload();
    });
  }

  if (!data) return null;
  const progress = data.goal ? Math.min(100, Math.round((data.this_week / data.goal) * 100)) : null;

  return (
    <section className="fitnessCard" aria-label="Activity">
      <div className="fitnessCardHead">
        <h2>Activity</h2>
        <HelpTip label="How points work">
          Points are hours × effort × 10, with effort from the kind of activity (a run counts more than a
          walk). They&rsquo;re worked out when you log it and never change after. Weeks run Monday to Sunday.
        </HelpTip>
      </div>

      <p className="activityWeek">
        <strong>{data.this_week}</strong> points this week{data.goal ? ` of ${data.goal}` : ""}
      </p>
      {progress !== null && (
        <div className="activityBar" role="progressbar" aria-label="This week against your goal"
             aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <span style={{ width: `${progress}%` }} />
        </div>
      )}

      <div className="activityGoal">
        <label className="calField">
          <span className="calFieldLabel">Weekly goal</span>
          <input type="number" min={1} max={10000} className="calInput" value={goal}
                 onChange={(e) => setGoal(e.target.value)} />
        </label>
        <button type="button" className="calButton" disabled={busy || !goal}
                onClick={() => saveGoal(Number(goal))}>Save goal</button>
        {data.goal !== null && (
          <button type="button" className="calButton" disabled={busy} onClick={() => saveGoal(null)}>No goal</button>
        )}
      </div>
      <p className="small-text muted activitySuggestion">
        {data.suggestion.points !== null ? (
          <>
            Suggested: {data.suggestion.points}. {data.suggestion.reason}{" "}
            {data.suggestion.points !== data.goal && (
              <button type="button" className="courseLinkAdd" disabled={busy}
                      onClick={() => saveGoal(data.suggestion.points)}>Use it</button>
            )}
          </>
        ) : data.suggestion.reason}
      </p>

      <form className="activityForm" onSubmit={log}>
        <select className="calInput" value={kind} onChange={(e) => setKind(e.target.value as ActivityKind)}
                aria-label="Kind of activity">
          {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
        </select>
        <input type="number" min={1} max={600} className="calInput" value={minutes} aria-label="Minutes"
               onChange={(e) => setMinutes(e.target.value)} />
        <input type="date" className="calInput" value={onDate} aria-label="Day"
               onChange={(e) => setOnDate(e.target.value)} />
        <input className="calInput" value={note} maxLength={120} placeholder="Note (optional)" aria-label="Note"
               onChange={(e) => setNote(e.target.value)} />
        <button type="submit" className="calButton calButtonPrimary" disabled={busy || !minutes}>Log</button>
      </form>
      {error && <p className="calError" role="alert">{error}</p>}

      {data.recent.length > 0 && (
        <ul className="activityList" aria-label="Recent activity">
          {data.recent.map((activity) => (
            <li key={activity.id}>
              <span>
                {shortDate(activity.on_date)} · {LABEL[activity.kind]} · {activity.minutes} min ·{" "}
                <strong>{activity.points}</strong>
                {activity.note && <span className="small-text muted"> · {activity.note}</span>}
              </span>
              {confirming === activity.id ? (
                <span className="activityConfirm">
                  <button type="button" className="calButton" disabled={busy}
                          onClick={() => void remove(activity.id)}>Yes, delete</button>
                  <button type="button" className="calButton" onClick={() => setConfirming(null)}>Keep</button>
                </span>
              ) : (
                <button type="button" className="courseLinkAdd" onClick={() => setConfirming(activity.id)}
                        aria-label={`Delete ${LABEL[activity.kind]} on ${shortDate(activity.on_date)}`}>
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
