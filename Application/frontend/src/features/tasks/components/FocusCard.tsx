import { useEffect, useState } from "react";
import HelpTip from "../../../shared/components/HelpTip";
import { duration } from "../../../shared/utils/dateUtils";
import { CourseFocus, fetchFocus, FocusSummary, startFocus, stopFocus } from "../focusApi";

/** Whose focus. */
interface FocusCardProps {
  readonly userId: string;
}

/** Minutes since a naive-UTC start, for the running clock. */
function elapsed(startedAt: string, now: number): number {
  return Math.max(0, Math.floor((now - Date.parse(`${startedAt}Z`)) / 60000));
}

/** Each course a dot: hours focused this term across, grade now up. */
function HoursAgainstGrade({ courses }: { courses: CourseFocus[] }) {
  const points = courses.filter((c) => c.grade !== null && c.minutes_term > 0);
  if (points.length < 2) return null;
  const maxH = Math.max(...points.map((c) => c.minutes_term / 60));
  const W = 260, H = 130, P = 22;
  const x = (h: number) => P + (h / maxH) * (W - 2 * P);
  const y = (g: number) => H - P - (g / 100) * (H - 2 * P);
  return (
    <figure className="focusChart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Hours focused this term against each course's grade">
        <line className="focusAxis" x1={P} y1={H - P} x2={W - P} y2={H - P} />
        <line className="focusAxis" x1={P} y1={P} x2={P} y2={H - P} />
        {points.map((c) => (
          <g key={c.course_code}>
            <circle className="focusDot" cx={x(c.minutes_term / 60)} cy={y(c.grade as number)} r={4} />
            <text className="focusLabel" x={x(c.minutes_term / 60) + 6} y={y(c.grade as number) + 3}>{c.course_code}</text>
          </g>
        ))}
      </svg>
      <figcaption className="small-text muted">Hours this term across, grade now up. Your courses only.</figcaption>
    </figure>
  );
}

/**
 * Focus sessions (Phase 4 item 4): a timer tagged per course. One at a time; a timer
 * forgotten past 12 hours records nothing. The week's minutes per course, and hours this
 * term against each course's grade once two courses have both.
 */
export default function FocusCard({ userId }: FocusCardProps) {
  const [data, setData] = useState<FocusSummary | null>(null);
  const [course, setCourse] = useState<string>("");
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setData(await fetchFocus(userId));
    } catch {
      setData(null);
    }
  }

  useEffect(() => { void load(); }, [userId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!data?.running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, [data?.running]);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      setNow(Date.now());
      await load();
    } catch {
      setError("Couldn't do that. Try again in a moment.");
    }
  }

  if (!data) return null;
  const real = data.courses.filter((c) => c.course_id !== null);

  return (
    <section className="focusCard" aria-label="Focus">
      <div className="labelWithTip">
        <h2 className="taskGroupTitle focusTitle">Focus</h2>
        <HelpTip label="How focus sessions work">
          Start the timer when you sit down to study, on a course or on nothing in particular, and stop it when
          you&apos;re done. One runs at a time. A timer left running for more than 12 hours was forgotten, so it
          records nothing.
        </HelpTip>
      </div>

      {data.running ? (
        <div className="focusRow">
          <span>
            <strong>{data.running.course_code ?? "Focusing"}</strong>{" "}
            <span className="muted">{duration(elapsed(data.running.started_at, now)) || "just started"}</span>
          </span>
          <button type="button" className="calButton" onClick={() => void act(() => stopFocus(userId))}>Stop</button>
        </div>
      ) : (
        <div className="focusRow">
          <select className="focusSelect" value={course} onChange={(e) => setCourse(e.target.value)}
            aria-label="Course to focus on">
            <option value="">No particular course</option>
            {real.map((c) => <option key={c.course_id} value={c.course_id as string}>{c.course_code}</option>)}
          </select>
          <button type="button" className="calButton" onClick={() => void act(() => startFocus(userId, course || null))}>
            Start
          </button>
        </div>
      )}
      {error && <p className="small-text error">{error}</p>}

      {data.total_this_week > 0 && (
        <ul className="focusWeek small-text">
          {data.courses.filter((c) => c.minutes_this_week > 0).map((c) => (
            <li key={c.course_code}><span>{c.course_code}</span> <strong>{duration(c.minutes_this_week)}</strong></li>
          ))}
          <li className="muted">This week <strong>{duration(data.total_this_week)}</strong></li>
        </ul>
      )}
      <HoursAgainstGrade courses={data.courses} />
    </section>
  );
}
