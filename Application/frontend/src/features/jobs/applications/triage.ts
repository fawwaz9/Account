import { addDays } from "../../../shared/utils/dateUtils";
import { Application, OPEN_STATUSES } from "./types";

/**
 * Which applications the tracker shows without being asked (D9). A season can
 * hold hundreds, nearly all finished or still waiting with nothing to do, so
 * the page lists only what needs you and leaves the rest to search.
 */

/** A deadline this close is worth seeing. */
export const DEADLINE_DAYS = 14;
/** A follow-up due this soon, or overdue. */
export const FOLLOW_UP_DAYS = 7;

/** Further along than "applied": a reply came, so there is something going on. */
const ACTIVE: Application["status"][] = ["offer", "interview", "screening"];

export interface Arranged {
  /** Offers, interviews, screenings, and anything with a date coming up. */
  needsYou: Application[];
  /** Quiet for 30 days while waiting on them (D3): "no reply yet?". */
  quiet: Application[];
  /** Applied, not quiet yet, nothing due: nothing to do but wait. */
  waiting: Application[];
  finished: Application[];
}

const isOpen = (item: Application) => OPEN_STATUSES.includes(item.status);

/** Has a deadline or follow-up close enough to act on. */
export function dueSoon(item: Application, today: string): boolean {
  const deadline = item.deadline !== null && item.deadline >= today && item.deadline <= addDays(today, DEADLINE_DAYS);
  const followUp = item.follow_up_on !== null && item.follow_up_on <= addDays(today, FOLLOW_UP_DAYS);
  return deadline || followUp;
}

/** The soonest date that put it on the list, for ordering: "9999" when none. */
function soonest(item: Application, today: string): string {
  const dates = [item.deadline, item.follow_up_on].filter((day): day is string => day !== null && dueSoon(item, today));
  return dates.sort()[0] ?? "9999";
}

/**
 * Split a season's applications. An active one goes in "needs you" even when
 * it has gone quiet: an interview with no news is still an interview. Needs
 * you runs offers first, then interviews, screenings, and the soonest date.
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

/**
 * Search: every word typed must appear in the company, role, location or
 * source, ignoring case. Nothing typed matches nothing -- the search shows
 * results only once you ask.
 */
export function matches(item: Application, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return false;
  const haystack = [item.company, item.role, item.location, item.source]
    .filter(Boolean).join(" ").toLowerCase();
  return words.every((word) => haystack.includes(word));
}
