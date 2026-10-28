import { addDays } from "../../../shared/utils/dateUtils";
import { Application, OPEN_STATUSES } from "./types";

/** Which applications the tracker shows unasked: only what needs you; search finds the rest. */

/** A deadline within this many days puts an application on the list. */
export const DEADLINE_DAYS = 14;
/** A follow-up due within this many days, or overdue, does too. */
export const FOLLOW_UP_DAYS = 7;

/** Statuses past applied, in needs-you order: a reply came. */
const ACTIVE: Application["status"][] = ["offer", "interview", "screening"];

/** A season's applications sorted into the tracker's groups. */
export interface Arranged {
  /** Offers, interviews, screenings, and anything with a date coming up. */
  needsYou: Application[];
  /** Waiting on them for 30 days: time to ask "no reply yet?". */
  quiet: Application[];
  /** Applied, not quiet yet, nothing due: nothing to do but wait. */
  waiting: Application[];
  /** Accepted, rejected, no reply or withdrawn. */
  finished: Application[];
}

/** True while the application is still in play. */
const isOpen = (item: Application) => OPEN_STATUSES.includes(item.status);

/** Has a deadline or follow-up close enough to act on. */
export function dueSoon(item: Application, today: string): boolean {
  const deadline = item.deadline !== null && item.deadline >= today && item.deadline <= addDays(today, DEADLINE_DAYS);
  const followUp = item.follow_up_on !== null && item.follow_up_on <= addDays(today, FOLLOW_UP_DAYS);
  return deadline || followUp;
}

/** The earliest date that put it on the list, for sorting; "9999" when none. */
function soonest(item: Application, today: string): string {
  const dates = [item.deadline, item.follow_up_on].filter((day): day is string => day !== null && dueSoon(item, today));
  return dates.sort()[0] ?? "9999";
}

/**
 * Split applications into needs you, quiet, waiting and finished.
 * Active ones always need you, even when quiet; offers first, then by soonest date.
 */
export function arrange(applications: Application[], today: string): Arranged {
  const out: Arranged = { needsYou: [], quiet: [], waiting: [], finished: [] };
  for (const item of applications) {
    if (!isOpen(item)) out.finished.push(item);
    else if (ACTIVE.includes(item.status) || dueSoon(item, today)) out.needsYou.push(item);
    else if (item.quiet) out.quiet.push(item);
    else out.waiting.push(item);
  }
  const rank = (item: Application) => {
    const at = ACTIVE.indexOf(item.status);
    return at === -1 ? ACTIVE.length : at;
  };
  out.needsYou.sort((a, b) => rank(a) - rank(b) || soonest(a, today).localeCompare(soonest(b, today)));
  // Longest silent first: the likeliest to really be no reply.
  out.quiet.sort((a, b) => a.last_step_on.localeCompare(b.last_step_on));
  return out;
}

/** Search: every typed word appears in company, role, location or source; empty matches nothing. */
export function matches(item: Application, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return false;
  const haystack = [item.company, item.role, item.location, item.source]
    .filter(Boolean).join(" ").toLowerCase();
  return words.every((word) => haystack.includes(word));
}
