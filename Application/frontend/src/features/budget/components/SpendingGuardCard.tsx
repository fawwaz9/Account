import { useEffect, useState } from "react";
import { fetchSpendingGuard } from "../api";
import { SpendingGuard } from "../types";
import { formatMoney } from "../money";

/** Whose money, and a counter the page bumps to refetch. */
interface SpendingGuardCardProps {
  readonly userId: string;
  readonly nonce: number;
}

/** "2 exams, 3 deadlines and 4 tasks" from a week's counts, leaving out the zeros. */
export function loadWords(week: { exams: number; deadlines: number; tasks: number }): string {
  const parts = [
    [week.exams, "exam"], [week.deadlines, "deadline"], [week.tasks, "task"],
  ].filter(([n]) => (n as number) > 0).map(([n, w]) => `${n} ${w}${n === 1 ? "" : "s"}`);
  if (parts.length <= 1) return parts.join("");
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * The deadline spending guard (Phase 4 item 13, §13.5): before a crunch week, the
 * categories you've spent more on in crunch weeks before. Shows only when there's a
 * crunch week ahead and a real spike to name; framed as a heads-up, not permission.
 */
export default function SpendingGuardCard({ userId, nonce }: SpendingGuardCardProps) {
  const [guard, setGuard] = useState<SpendingGuard | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSpendingGuard(userId)
      .then((next) => { if (!cancelled) setGuard(next); })
      .catch(() => { if (!cancelled) setGuard(null); });
    return () => { cancelled = true; };
  }, [userId, nonce]);

  if (!guard?.ready || !guard.upcoming || guard.lifts.length === 0) return null;
  const week = guard.upcoming;
  const when = new Date(`${week.starts_on}T00:00:00`).toLocaleDateString(undefined,
    { weekday: "short", month: "short", day: "numeric" });

  return (
    <section className="spendingGuard" aria-label="Crunch week ahead">
      <h2 className="spendingGuardTitle">A heavy week from {when}</h2>
      <p className="small-text">{loadWords(week)}. In weeks like that, you&apos;ve spent more on:</p>
      <ul className="spendingGuardList">
        {guard.lifts.map((c) => (
          <li key={c.category}>
            <strong>{c.category}</strong>: about {formatMoney(c.crunch_weekly)} a week, against{" "}
            {formatMoney(c.usual_weekly)} usually <span className="muted small-text">({c.lift}× over {c.crunch_weeks} crunch weeks)</span>
          </li>
        ))}
      </ul>
      <p className="small-text muted">{guard.note}</p>
    </section>
  );
}
