import { ShiftOccurrence } from "./types";
import { addDays } from "../../shared/utils/dateUtils";

/** How far back the list looks for a past shift nobody confirmed; `useJobs` fetches this far. */
export const UNCONFIRMED_DAYS = 90;

/** How long a confirmed shift stays in the list after its date. */
export const CONFIRMED_DAYS = 20;

/** How far ahead the list, and a job card's hours, reach. */
export const AHEAD_DAYS = 21;

/**
 * Shift list order: unconfirmed past shifts nearest first, then upcoming soonest first,
 * then confirmed shifts from the last 20 days, most recent first.
 */
export function arrangeShifts(shifts: ShiftOccurrence[], today: string): ShiftOccurrence[] {
  const confirmedFrom = addDays(today, -CONFIRMED_DAYS);
  const byDate = (a: ShiftOccurrence, b: ShiftOccurrence) =>
    a.on_date.localeCompare(b.on_date) || (a.scheduled_start ?? "").localeCompare(b.scheduled_start ?? "");

  const needing = shifts.filter((shift) => shift.assumed).sort((a, b) => byDate(b, a));
  const upcoming = shifts.filter((shift) => !shift.assumed && !shift.confirmed).sort(byDate);
  const confirmed = shifts
    .filter((shift) => shift.confirmed && shift.on_date >= confirmedFrom)
    .sort((a, b) => byDate(b, a));

  return [...needing, ...upcoming, ...confirmed];
}

/** Counted minutes per job from today to three weeks out, for each job card. */
export function upcomingMinutesByJob(shifts: ShiftOccurrence[], today: string): Map<string, number> {
  const until = addDays(today, AHEAD_DAYS);
  const totals = new Map<string, number>();
  for (const shift of shifts) {
    if (shift.on_date < today || shift.on_date > until) continue;
    totals.set(shift.job_id, (totals.get(shift.job_id) ?? 0) + shift.counted_minutes);
  }
  return totals;
}
