import { useEffect, useState } from "react";
import { fetchDigest } from "./api";
import { Digest } from "./types";
import { useApiRefreshCount } from "../../shared/hooks/useApiRefresh";

/** Whose day. */
interface TodayCardProps {
  readonly userId: string;
}

/** Where each line of the digest belongs, by how it starts, for its styling. */
function tone(line: string): string {
  if (line.startsWith("At risk:") || line.startsWith("Overdue:")) return "todayLine todayLineWarn";
  if (line.startsWith("Exam:")) return "todayLine todayLineExam";
  return "todayLine";
}

/**
 * The Today card (Phase 4 item 6): the digest's own lines, so it says exactly what the
 * briefing says. Renders nothing while loading or when the digest can't be read.
 */
export default function TodayCard({ userId }: TodayCardProps) {
  const [digest, setDigest] = useState<Digest | null>(null);
  const refreshed = useApiRefreshCount();

  useEffect(() => {
    let cancelled = false;
    fetchDigest(userId)
      .then((next) => { if (!cancelled) setDigest(next); })
      .catch(() => { if (!cancelled) setDigest(null); });
    return () => { cancelled = true; };
  }, [userId, refreshed]);

  if (!digest) return null;

  const [heading, ...lines] = digest.text.split("\n");

  return (
    <section className="gradeSummary todayCard" aria-label="Today">
      <h2 className="todayTitle">
        Today <span className="muted todayDate">{heading.replace(/\.$/, "")}</span>
      </h2>
      <ul className="todayLines">
        {lines.map((line) => <li key={line} className={tone(line)}>{line}</li>)}
      </ul>
    </section>
  );
}
