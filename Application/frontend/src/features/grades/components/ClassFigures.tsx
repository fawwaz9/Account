import { useEffect, useRef, useState } from "react";
import { fetchClassFigures } from "../api";
import { ClassFigures as Figures, TermDistribution } from "../types";
import HelpTip from "../../../shared/components/HelpTip";

/** The course to read, and a counter the page bumps to refetch. */
interface ClassFiguresProps {
  readonly userId: string;
  readonly courseId: string;
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

/**
 * "How past classes did": each finished term's grade bands from students who shared, with the
 * median and your own band marked; a one-line wait below the floor, nothing for an uncountable course.
 */
export default function ClassFigures({ userId, courseId, nonce }: ClassFiguresProps) {
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
    <section className="classFigures" aria-label="How past classes did">
      <div className="classFiguresHead">
        <span className="classFiguresLabel">How past classes did</span>
        <HelpTip label="About class figures">
          Grades students chose to share at the end of a term, counted with no names. A term is shown
          once {figures.floor} students have shared and its sharing window has closed, so the
          figures never move with one person&rsquo;s answer.
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

      {!term ? (
        <p className="classFiguresWait">
          Shown once {figures.floor} students in a finished term have shared their grade.
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
