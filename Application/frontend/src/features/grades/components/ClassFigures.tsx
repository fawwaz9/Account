import { useEffect, useRef, useState } from "react";
import { checkInOfficeHours, fetchClassFigures, undoOfficeHoursCheckIn } from "../api";
import {
  ClassFigures as Figures, CourseIntel, OfficeHourCheckIn, OfficeHourSlot, OfficeHourWait, TermDistribution,
} from "../types";
import HelpTip from "../../../shared/components/HelpTip";

/** The course to read, and a counter the page bumps to refetch. */
interface ClassFiguresProps {
  readonly userId: string;
  readonly courseId: string;
  /** In the current term: office hours are offered only then. */
  readonly current: boolean;
  /** Bumped by the page when a grade changes, so "you" moves. */
  readonly nonce: number;
}

/** A band's range as read: "80–84", "Below 50", "95–100". */
export function bandLabel(bucket: number): string {
  if (bucket === 0) return "Below 50";
  if (bucket >= 95) return "95–100";
  return `${bucket}–${bucket + 4}`;
}

/** Every band from the lowest to the highest held, gaps included, so the shape is honest. */
export function filledBands(term: TermDistribution): { bucket: number; contributors: number }[] {
  const held = new Map(term.bands.map((band) => [band.bucket, band.contributors]));
  const buckets = term.bands.map((band) => band.bucket);
  const low = Math.min(...buckets);
  const high = Math.max(...buckets);
  const out: { bucket: number; contributors: number }[] = [];
  // Below 50 is one band, then 50, 55 ... 95.
  for (let bucket = low; bucket <= high; bucket = bucket === 0 ? 50 : bucket + 5) {
    out.push({ bucket, contributors: held.get(bucket) ?? 0 });
  }
  return out;
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** A local weekday and hour as read: "Tue 2pm". */
export function slotLabel(weekday: number, hour: number): string {
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${WEEKDAYS[weekday]} ${twelve}${hour < 12 ? "am" : "pm"}`;
}

/** How a slot's line usually is, in words. */
const READINGS: Record<OfficeHourWait, string> = {
  none: "usually no line",
  short: "usually a short line",
  long: "usually a long line",
};

/** What past students' reviews say, as label and reading pairs; only figures above the floor. */
export function intelLines(intel: CourseIntel): { label: string; value: string; from: number }[] {
  const lines: { label: string; value: string; from: number }[] = [];
  if (intel.hours_median !== null && intel.hours_answers !== null) {
    lines.push({ label: "Hours a week", value: `about ${intel.hours_median}`, from: intel.hours_answers });
  }
  if (intel.difficulty_mean !== null && intel.difficulty_answers !== null) {
    lines.push({ label: "Difficulty", value: `${intel.difficulty_mean} / 5`, from: intel.difficulty_answers });
  }
  if (intel.clarity_mean !== null && intel.clarity_answers !== null) {
    lines.push({ label: "Instructor clarity", value: `${intel.clarity_mean} / 5`, from: intel.clarity_answers });
  }
  if (intel.again_share !== null && intel.again_answers !== null) {
    lines.push({ label: "Would take it again", value: `${intel.again_share}%`, from: intel.again_answers });
  }
  return lines;
}

/**
 * "From past students": what their term reviews say, then each finished term's grade bands with
 * the median and your band marked; a one-line wait below the floor, nothing for an uncountable course.
 */
export default function ClassFigures({ userId, courseId, current, nonce }: ClassFiguresProps) {
  const [figures, setFigures] = useState<Figures | null>(null);
  const [termCode, setTermCode] = useState<string | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    const ticket = ++latestRequest.current;
    let cancelled = false;
    fetchClassFigures(userId, courseId)
      .then((result) => {
        if (!cancelled && ticket === latestRequest.current) setFigures(result);
      })
      .catch(() => {
        if (!cancelled && ticket === latestRequest.current) setFigures(null);
      });
    return () => { cancelled = true; };
  }, [userId, courseId, nonce]);

  if (!figures || figures.course_key === null) return null;

  const terms = figures.distributions;
  const term = terms.find((t) => t.term_code === termCode) ?? terms[0];

  return (
    <section className="classFigures" aria-label="From past students">
      <div className="classFiguresHead">
        <span className="classFiguresLabel">From past students</span>
        <HelpTip label="About these figures">
          What students said in their end-of-term reviews, and the grades they chose to share, counted
          with no names. Each figure is shown once {figures.floor} students have given it and their
          term&rsquo;s review window has closed, so nothing moves with one person&rsquo;s answer.
        </HelpTip>
        {terms.length > 1 && (
          <select
            className="calInput classFiguresTerm"
            aria-label="Term"
            value={term.term_code}
            onChange={(event) => setTermCode(event.target.value)}
          >
            {terms.map((t) => (
              <option key={t.term_code} value={t.term_code}>{t.term_label}</option>
            ))}
          </select>
        )}
      </div>

      {figures.intel && (
        <dl className="classFiguresIntel">
          {intelLines(figures.intel).map((line) => (
            <div key={line.label}>
              <dt>{line.label}</dt>
              <dd>
                {line.value} <span className="classFiguresMark">({line.from})</span>
              </dd>
            </div>
          ))}
        </dl>
      )}

      {current && (
        <OfficeHours userId={userId} courseId={courseId} slots={figures.office_hours} floor={figures.floor} />
      )}

      {!term ? (
        <p className="classFiguresWait">
          {figures.intel ? "Grades shown" : "Shown"} once {figures.floor} students in a finished term
          have shared {figures.intel ? "theirs" : "their grade"}.
        </p>
      ) : (
        <TermBands term={term} yourBucket={figures.your_bucket} yourGrade={figures.your_grade} />
      )}
    </section>
  );
}

/** One term's bands as bars, the median and your band marked, with a one-line summary. */
function TermBands({ term, yourBucket, yourGrade }: {
  term: TermDistribution;
  yourBucket: number | null;
  yourGrade: number | null;
}) {
  const bands = filledBands(term);
  const most = Math.max(...bands.map((band) => band.contributors));
  return (
    <>
      <p className="classFiguresSummary">
        {term.term_label} · {term.contributors} students · median {bandLabel(term.median_bucket)}
        {yourGrade !== null && yourBucket !== null && (
          <> · you: {Math.round(yourGrade * 10) / 10}%</>
        )}
      </p>
      <ul className="classFiguresBands" aria-label={`Grades in ${term.term_label}`}>
        {bands.map((band) => {
          const marks = [
            band.bucket === term.median_bucket ? "median" : null,
            band.bucket === yourBucket ? "you" : null,
          ].filter(Boolean);
          return (
            <li key={band.bucket} className={band.bucket === yourBucket ? "classFiguresYours" : undefined}>
              <span className="classFiguresBandLabel">{bandLabel(band.bucket)}</span>
              <span className="classFiguresTrack">
                <span
                  className="classFiguresBar"
                  style={{ width: `${most ? (band.contributors / most) * 100 : 0}%` }}
                />
              </span>
              <span className="classFiguresCount">
                {band.contributors}
                {marks.length > 0 && <span className="classFiguresMark"> {marks.join(", ")}</span>}
              </span>
            </li>
          );
        })}
      </ul>
    </>
  );
}

/** The office-hours radar: three taps to say how the line is, then the slots it's usually busy. */
function OfficeHours({ userId, courseId, slots, floor }: {
  userId: string;
  courseId: string;
  slots: OfficeHourSlot[];
  floor: number;
}) {
  const [made, setMade] = useState<OfficeHourCheckIn | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function tell(wait: OfficeHourWait) {
    setError(null);
    try {
      setMade(await checkInOfficeHours(userId, courseId, wait));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't check in");
    }
  }

  async function undo() {
    if (!made) return;
    setError(null);
    try {
      await undoOfficeHoursCheckIn(userId, made.id);
      setMade(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't undo it");
    }
  }

  return (
    <div className="classFiguresOffice">
      <p className="classFiguresOfficeAsk">
        At office hours now? Say how the line is, and everyone sees when it&rsquo;s usually busy.
      </p>
      <div className="classFiguresOfficeButtons" role="group" aria-label="How's the line?">
        {(["none", "short", "long"] as const).map((wait) => (
          <button
            key={wait}
            type="button"
            className="calButton"
            aria-pressed={made?.wait === wait}
            onClick={() => void tell(wait)}
          >
            {wait === "none" ? "No line" : wait === "short" ? "Short" : "Long"}
          </button>
        ))}
      </div>
      {made && (
        <p className="classFiguresOfficeDone">
          Counted for {slotLabel(made.weekday, made.hour)}.{" "}
          <button type="button" className="courseLinkAdd" onClick={() => void undo()}>Undo</button>
        </p>
      )}
      {error && <p className="classFiguresOfficeDone" role="alert">{error}</p>}
      {slots.length > 0 ? (
        <ul className="classFiguresSlots" aria-label="Office hours, usually">
          {slots.map((slot) => (
            <li key={`${slot.weekday}-${slot.hour}`}>
              {slotLabel(slot.weekday, slot.hour)}: {READINGS[slot.reading]}{" "}
              <span className="classFiguresMark">({slot.people})</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="classFiguresWait">Busy times show once {floor} people have checked in at the same hour.</p>
      )}
    </div>
  );
}
