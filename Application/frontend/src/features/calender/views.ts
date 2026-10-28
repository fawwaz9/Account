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

/** The calendar's views: a month, or one, three or seven days against the clock. */
export type CalendarView = "month" | "week" | "3day" | "day";

// The app's one phone breakpoint, re-exported for the calendar's callers.
export { PHONE_QUERY } from "../../shared/hooks/useMediaQuery";

/** Views the switch offers, in order: day, 3-day and month on a phone; week and month otherwise. */
export function viewsFor(phone: boolean): CalendarView[] {
  return phone ? ["day", "3day", "month"] : ["week", "month"];
}

/** The view a phone (3-day) or a desktop (week) opens on. */
export function defaultView(phone: boolean): CalendarView {
  return phone ? "3day" : "week";
}

/** `view` if this width offers it, else that width's default; for crossing the breakpoint. */
export function fitView(view: CalendarView, phone: boolean): CalendarView {
  if (viewsFor(phone).includes(view)) return view;
  return phone ? "3day" : "week";
}

/** The dates a view shows for the cursor; day and 3-day start at the cursor, not the week. */
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

/** Move the cursor by `direction` pages of the current view. */
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

/** The heading between the arrows for a view and cursor. */
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

/** A view's button text in the switch. */
export function viewName(view: CalendarView): string {
  return { day: "Day", "3day": "3 day", week: "Week", month: "Month" }[view];
}
