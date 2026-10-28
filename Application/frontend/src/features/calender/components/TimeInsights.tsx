import { useEffect, useMemo, useRef, useState } from "react";
import { fetchCrunch, fetchFreeBlocks, fetchWeekLoad } from "../api";
import { CrunchStrip, FreeBlock, WeekLoad } from "../types";
import { clockTime, duration, fromIso } from "../../../shared/utils/dateUtils";

/** The week on screen, the crunch horizon's end, the user, and a refetch counter. */
interface TimeInsightsProps {
  /** Monday of the week on screen, YYYY-MM-DD; `weekEnd` is its Sunday. */
  readonly weekStart: string;
  readonly weekEnd: string;
  /** End of the horizon the crunch strip covers. */
  readonly horizonEnd: string;
  readonly userId: string;
  readonly nonce: number;
}

/**
 * The week's load, its free blocks (two per day until expanded), and the crunch of weeks ahead.
 * Renders nothing when all three are empty or the read fails.
 */
export default function TimeInsights({
  weekStart, weekEnd, horizonEnd, userId, nonce,
}: TimeInsightsProps) {
  const [blocks, setBlocks] = useState<FreeBlock[]>([]);
  const [load, setLoad] = useState<WeekLoad | null>(null);
  const [strip, setStrip] = useState<CrunchStrip | null>(null);
  const [showAllBlocks, setShowAllBlocks] = useState(false);
  // The week can be changed faster than these return, and an older answer
  // landing last would describe a week that is no longer on screen.
  const latestRequest = useRef(0);

  useEffect(() => {
    const ticket = ++latestRequest.current;
    let cancelled = false;
    setShowAllBlocks(false);

    Promise.all([
      fetchFreeBlocks(userId, weekStart, weekEnd),
      fetchWeekLoad(userId, weekStart, weekEnd),
      fetchCrunch(userId, weekStart, horizonEnd),
    ])
      .then(([nextBlocks, nextLoad, nextStrip]) => {
        if (cancelled || ticket !== latestRequest.current) return;
        setBlocks(nextBlocks);
        setLoad(nextLoad);
        setStrip(nextStrip);
      })
      .catch(() => {
        if (cancelled || ticket !== latestRequest.current) return;
        setBlocks([]);
        setLoad(null);
        setStrip(null);
      });

    return () => { cancelled = true; };
  }, [userId, weekStart, weekEnd, horizonEnd, nonce]);

  /**
   * At most two gaps per day in the collapsed list.
   *
   * The server ranks every block in the week by length, which let one day fill
   * the whole list — five empty days at fourteen hours each pushed Friday's
   * real ten-hour gap off the end, and it was truncated silently so it looked
   * like the gap had not been found at all.
   *
   * The cap applies only while collapsed. Expanding shows every block, uncapped,
   * so nothing is ever unreachable.
   */
  const rankedBlocks = useMemo(() => {
    const perDay = new Map<string, number>();
    return blocks.filter((block) => {
      const seen = perDay.get(block.on_date) ?? 0;
      if (seen >= 2) return false;
      perDay.set(block.on_date, seen + 1);
      return true;
    });
  }, [blocks]);

  const shownBlocks = showAllBlocks ? blocks : rankedBlocks.slice(0, 5);
  const hiddenBlocks = blocks.length - shownBlocks.length;

  const hasLoad = load && (load.booked_minutes > 0 || load.task_count > 0);
  const hasCrunch = strip && strip.peak > 0;
  if (!hasLoad && blocks.length === 0 && !hasCrunch) return null;

  return (
    <section className="timeInsights">
      {hasLoad && (
        <div className="loadLine">
          <span className="loadLabel">This week</span>
          <span className="loadFigures">
            {load.booked_minutes > 0 && (
              <span>{duration(load.booked_minutes)} booked</span>
            )}
            {load.estimated_minutes > 0 && (
              <span>
                {duration(load.estimated_minutes)} estimated
                {load.estimate_ratio != null && ` (yours × ${load.estimate_ratio.toFixed(2)})`}
              </span>
            )}
            <span>
              {load.task_count} {load.task_count === 1 ? "task" : "tasks"}
            </span>
            {/* Said plainly: an hours figure built from a third of the tasks is
                not the week's real load, and quietly looks like it is. */}
            {load.unestimated_tasks > 0 && (
              <span className="loadMuted">
                {load.unestimated_tasks} with no estimate
              </span>
            )}
          </span>
        </div>
      )}

      {blocks.length > 0 && (
        <div className="freeBlocks">
          <h3 className="insightHeading">Free blocks</h3>
          <ul className="freeBlockList">
            {shownBlocks.map((block) => (
              <li key={`${block.on_date}-${block.starts_at}`}>
                <span className="freeBlockDay">
                  {fromIso(block.on_date).toLocaleDateString(undefined, {
                    weekday: "short", day: "numeric", month: "short",
                  })}
                </span>
                <span className="freeBlockSpan">
                  {clockTime(block.starts_at)}–{clockTime(block.ends_at)}
                </span>
                <span className="freeBlockLength">{duration(block.minutes)}</span>
              </li>
            ))}
          </ul>

          {/* A count rather than silent truncation, and clickable because the
              whole problem was looking for a block that was there and not
              finding it. */}
          {hiddenBlocks > 0 && (
            <button
              type="button"
              className="freeBlockMore"
              onClick={() => setShowAllBlocks(true)}
            >
              +{hiddenBlocks} more
            </button>
          )}
          {showAllBlocks && blocks.length > 5 && (
            <button
              type="button"
              className="freeBlockMore"
              onClick={() => setShowAllBlocks(false)}
            >
              Show fewer
            </button>
          )}
        </div>
      )}

      {hasCrunch && (
        <div className="crunchRadar">
          <h3 className="insightHeading">Weeks ahead</h3>
          {/* Bars are a share of the heaviest week rather than of an arbitrary
              ceiling, so the shape means something even in a light term. */}
          <ul className="crunchStrip">
            {strip.weeks.map((week) => {
              const height = strip.peak > 0
                ? Math.max(6, Math.round((week.weight / strip.peak) * 100))
                : 6;
              const parts = [
                week.exams && `${week.exams} exam${week.exams === 1 ? "" : "s"}`,
                week.deadlines && `${week.deadlines} deadline${week.deadlines === 1 ? "" : "s"}`,
                week.tasks && `${week.tasks} task${week.tasks === 1 ? "" : "s"}`,
              ].filter(Boolean).join(", ");
              return (
                <li
                  key={week.starts_on}
                  className={week.is_current ? "crunchWeek crunchWeekNow" : "crunchWeek"}
                  title={`Week of ${week.starts_on}${parts ? ` — ${parts}` : " — quiet"}`}
                >
                  <span className="crunchBar" style={{ height: `${height}%` }} />
                </li>
              );
            })}
          </ul>
          <p className="crunchLegend">
            {strip.weeks.length} weeks · heaviest carries {strip.peak}
          </p>
        </div>
      )}
    </section>
  );
}
