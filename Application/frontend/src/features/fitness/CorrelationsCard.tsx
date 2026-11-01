import { useEffect, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import { Correlation, Correlations, fetchCorrelations } from "./api";

/** Whose weeks. */
interface CorrelationsCardProps {
  readonly userId: string;
}

const SIZE = 150;
const PAD = 14;

/** One dot per week: exertion across, the academic figure up. */
function Scatter({ c }: { c: Correlation }) {
  const maxX = Math.max(1, ...c.pairs.map((p) => p.body));
  const maxY = Math.max(1, ...c.pairs.map((p) => p.academic));
  const x = (v: number) => PAD + (v / maxX) * (SIZE - 2 * PAD);
  const y = (v: number) => SIZE - PAD - (v / maxY) * (SIZE - 2 * PAD);
  return (
    <svg className="corrScatter" viewBox={`0 0 ${SIZE} ${SIZE}`} role="img"
      aria-label={`${c.weeks} weeks of ${c.body_label.toLowerCase()} against ${c.academic_label.toLowerCase()}`}>
      <line className="corrAxis" x1={PAD} y1={SIZE - PAD} x2={SIZE - PAD} y2={SIZE - PAD} />
      <line className="corrAxis" x1={PAD} y1={PAD} x2={PAD} y2={SIZE - PAD} />
      {c.pairs.map((p) => <circle key={p.week_start} className="corrDot" cx={x(p.body)} cy={y(p.academic)} r={3} />)}
    </svg>
  );
}

/**
 * Cross-room correlations (Phase 4 item 8): exertion against finished work, week by week.
 * Quiet until eight weeks hold both; strength in words with the weeks behind it, and a
 * reminder that moving together isn't cause. No money anywhere in it (§13.3).
 */
export default function CorrelationsCard({ userId }: CorrelationsCardProps) {
  const [data, setData] = useState<Correlations | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCorrelations(userId)
      .then((next) => { if (!cancelled) setData(next); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [userId]);

  if (!data) return null;
  // Nothing in either room yet: not even a "waiting" line.
  if (!data.ready && data.weeks_of_both === 0) return null;

  return (
    <section className="fitnessCard" aria-label="Movement and your work">
      <div className="fitnessCardHead">
        <h2>Movement and your work</h2>
        <HelpTip label="How this is worked out">
          Each complete week&apos;s exertion points against the tasks, and the minutes of work, you finished that
          week, over the last six months. The link is Pearson&apos;s correlation, put into words.
        </HelpTip>
      </div>

      {!data.ready ? (
        <p className="small-text muted">
          Shows once both are logged for {data.needed_weeks} weeks: {data.weeks_of_both} so far.
        </p>
      ) : (
        <>
          {data.correlations.map((c) => (
            <div key={c.key} className="corrRow">
              <Scatter c={c} />
              <div>
                <p className="corrTitle">{c.body_label} and {c.academic_label.toLowerCase()}</p>
                <p className="small-text">{c.reading}</p>
              </div>
            </div>
          ))}
          <p className="small-text muted">{data.caution}</p>
        </>
      )}
    </section>
  );
}
