import {
  addDays,
  addMonths,
  firstOfMonth,
  fromIso,
  monthGrid,
  monthLabel,
  rangeLabel,
  shortDate,
  weekGrid,
  weekLabel,
} from "../../shared/utils/dateUtils";

/**
 * Which window of the calendar is on screen.
 *
 * A month of dates, or one, three or seven days against the clock. The week
 * is a desktop view and the day and three-day views are phone views: on a
 * phone seven columns are too narrow to read, and on a desktop one column is
 * a waste of the screen.
 */
export type CalendarView = "month" | "week" | "3day" | "day";

// The app's one phone breakpoint, re-exported for the calendar's callers.
export { PHONE_QUERY } from "../../shared/hooks/useMediaQuery";

/** The views the switch offers, in its order. */
export function viewsFor(phone: boolean): CalendarView[] {
  return phone ? ["day", "3day", "month"] : ["week", "month"];
}

/** What a phone opens on, and what a desktop does. */
export function defaultView(phone: boolean): CalendarView {
  return phone ? "3day" : "week";
}

/**
 * The nearest view this width can show, for when a rotation or a resize
 * crosses the breakpoint. Month exists on both; a week becomes three days and
 * back, which is the closest each side has to the other.
 */
export function fitView(view: CalendarView, phone: boolean): CalendarView {
  if (viewsFor(phone).includes(view)) return view;
  return phone ? "3day" : "week";
}

/**
 * The dates a view shows for a cursor.
 *
 * The day and three-day views start at the cursor rather than snapping to a
 * week, so "Today" shows today and the two days after it -- what a phone is
 * opened to check.
 */
export function windowDays(view: CalendarView, cursor: string): string[] {
  switch (view) {
    case "day":
      return [cursor];
    case "3day":
      return [cursor, addDays(cursor, 1), addDays(cursor, 2)];
    case "week":
      return weekGrid(cursor);
    case "month":
      return monthGrid(cursor);
  }
}

/** One press of an arrow: a whole page of whatever is on screen. */
export function stepCursor(view: CalendarView, cursor: string, direction: number): string {
  switch (view) {
    case "day":
      return addDays(cursor, direction);
    case "3day":
      return addDays(cursor, direction * 3);
    case "week":
      return addDays(cursor, direction * 7);
    case "month":
      return addMonths(firstOfMonth(cursor), direction);
  }
}

/** The heading between the arrows. */
export function viewLabel(view: CalendarView, cursor: string): string {
  switch (view) {
    case "day":
      return `${shortDate(cursor)} ${fromIso(cursor).getFullYear()}`;
    case "3day":
      return rangeLabel(cursor, addDays(cursor, 2));
    case "week":
      return weekLabel(cursor);
    case "month":
      return monthLabel(cursor);
  }
}

/** What one arrow press moves by, for its accessible name. */
export function stepNoun(view: CalendarView): string {
  return { day: "day", "3day": "3 days", week: "week", month: "month" }[view];
}

/** The switch's button text. */
export function viewName(view: CalendarView): string {
  return { day: "Day", "3day": "3 day", week: "Week", month: "Month" }[view];
}
