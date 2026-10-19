import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAgenda } from "../api";
import { EventOccurrence } from "../types";
import { fetchTasks } from "../../tasks/api";
import { fetchSharedTasks, SharedTask } from "../../tasks/sharing";
import { fetchSharedEvents, SharedEvent } from "../sharing";
import { fetchApplications } from "../../jobs/applications/api";
import { Application } from "../../jobs/applications/types";
import { Task } from "../../tasks/types";
import { useAuth } from "../../../app/auth/AuthContext";
import { today } from "../../../shared/utils/dateUtils";
import { useMediaQuery } from "../../../shared/hooks/useMediaQuery";
import {
  CalendarView,
  defaultView,
  fitView,
  PHONE_QUERY,
  stepCursor,
  viewLabel,
  viewsFor,
  windowDays,
} from "../views";
import { useApiRefresh } from "../../../shared/hooks/useApiRefresh";

export type { CalendarView } from "../views";

export interface CalendarDay {
  date: string;
  occurrences: EventOccurrence[];
  tasks: Task[];
}

/**
 * One window of the calendar -- a month, or a week, three days or one day
 * against the clock -- with events expanded by the API and the tasks due in
 * the same span.
 *
 * Two requests rather than one combined endpoint, because a deadline is edited
 * on the task and a lecture is edited on the event -- merging them server-side
 * would create a third shape that belongs to neither and has to be unpicked
 * before anything can be saved.
 */
export function useCalender() {
  const { user } = useAuth();
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;
  // A phone gets the day and three-day views in place of the week, whose seven
  // columns are too narrow to read there (views.ts).
  const phone = useMediaQuery(PHONE_QUERY);
  // A time axis by default -- the week, or three days on a phone: it is the
  // view that answers "what does today actually look like" and the one the
  // free blocks and week load hang off.
  const [chosenView, setView] = useState<CalendarView>(() => defaultView(phone));
  // Read through fitView rather than corrected in an effect, so a rotation that
  // crosses the breakpoint never renders, or fetches, a view the width does not
  // offer. The choice itself is kept: rotate back and it is still there.
  const view = fitView(chosenView, phone);
  // One anchor for every view, so switching between them stays where you were
  // rather than jumping back to today.
  const [cursor, setCursor] = useState(today());
  const [occurrences, setOccurrences] = useState<EventOccurrence[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The month grid runs from the Monday before the 1st to the Sunday after the
  // last, so the window has to cover those overflow days or the first and last
  // rows come back empty. The other views are simply their own days -- the
  // agenda endpoint takes any window, so no view needs anything of its own.
  const days = windowDays(view, cursor);
  const windowStart = days[0];
  const windowEnd = days[days.length - 1];

  // Every load takes a ticket and only the newest may write state. Stepping the
  // month quickly fires several at once, and without this October resolving
  // after November leaves October's events under November's heading -- the same
  // bug the budget month picker had (audit #12).
  const latestRequest = useRef(0);

  /** Step a whole page of whatever is on screen. */
  const step = useCallback(
    (direction: number) => {
      setCursor((current) => stepCursor(view, current, direction));
    },
    [view]
  );

  const load = useCallback(async () => {
    if (!userId) {
      setLoading(false);
      return;
    }

    const ticket = ++latestRequest.current;
    setLoading(true);
    setError(null);

    try {
      const [nextOccurrences, nextTasks, sharedEvents, sharedTasks, applications] = await Promise.all([
        fetchAgenda(userId, windowStart, windowEnd),
        fetchTasks(userId, { start: windowStart, end: windowEnd }),
        // Phase 2 item 9b. A failure here leaves your own calendar as it was
        // rather than taking it down with it.
        fetchSharedEvents(userId, windowStart, windowEnd).catch(() => [] as SharedEvent[]),
        fetchSharedTasks(userId).catch(() => [] as SharedTask[]),
        // Phase 3 item 1 (D4), likewise: the tracker failing leaves the
        // calendar as it was.
        fetchApplications(userId).catch(() => [] as Application[]),
      ]);
      if (ticket !== latestRequest.current) return;
      setOccurrences([
        ...nextOccurrences,
        ...sharedEvents.map(sharedEventOccurrence),
        ...sharedTasks
          .filter((task) => task.due_date && task.due_date >= windowStart && task.due_date <= windowEnd)
          .map(sharedTaskOccurrence),
        ...applicationOccurrences(applications, windowStart, windowEnd),
      ]);
      setTasks(nextTasks);
    } catch (err) {
      if (ticket !== latestRequest.current) return;
      setError(err instanceof Error ? err.message : "Could not load your calendar");
    } finally {
      if (ticket === latestRequest.current) setLoading(false);
    }
  }, [userId, windowStart, windowEnd]);

  // Catch up when a background refetch finds something new (audit #35).
  useApiRefresh(load);

  useEffect(() => {
    load();
  }, [load]);

  return {
    view,
    setView,
    phone,
    views: viewsFor(phone),
    label: viewLabel(view, cursor),
    cursor,
    setCursor,
    step,
    days: groupByDay(days, occurrences, tasks),
    occurrences,
    tasks,
    loading,
    error,
    reload: load,
  };
}

/** One bucket per grid square, so the view never filters inside a render loop. */
function groupByDay(
  days: string[],
  occurrences: EventOccurrence[],
  tasks: Task[]
): CalendarDay[] {
  const buckets = new Map<string, CalendarDay>(
    days.map((date) => [date, { date, occurrences: [], tasks: [] }])
  );

  for (const occurrence of occurrences) {
    buckets.get(occurrence.on_date)?.occurrences.push(occurrence);
  }
  for (const task of tasks) {
    if (task.due_date) buckets.get(task.due_date)?.tasks.push(task);
  }

  // Earliest deadline first, and anything without a time ahead of the rest --
  // an untimed task is due some time that day, so it cannot be ordered against
  // one due at nine and should not be guessed into the middle of them.
  for (const bucket of buckets.values()) {
    bucket.tasks.sort((a, b) => (a.due_time ?? "").localeCompare(b.due_time ?? ""));
  }

  return days.map((date) => buckets.get(date)!);
}

/** Someone else's event, as an occurrence on your calendar (Phase 2 item 9b). */
export function sharedEventOccurrence(event: SharedEvent): EventOccurrence {
  return {
    event_id: event.event_id, on_date: event.starts_on, title: event.title,
    kind: event.kind as EventOccurrence["kind"], start_time: event.start_time, end_time: event.end_time,
    location: event.location, notes: event.notes, course_id: null, course_code: null, job_id: null,
    repeats: false, grade_id: null,
    shared: { owner_name: event.owner_name, member_names: event.member_names, what: "event" },
  };
}

/**
 * Someone else's task, on the day it is due. Shown with the day's all-day
 * items rather than on the clock: it is a deadline, not a block of time.
 */
export function sharedTaskOccurrence(task: SharedTask): EventOccurrence {
  return {
    event_id: task.task_id, on_date: task.due_date as string, title: task.done ? `✓ ${task.title}` : task.title,
    kind: "deadline", start_time: null, end_time: null, location: null, notes: task.notes,
    course_id: null, course_code: null, job_id: null, repeats: false, grade_id: null,
    shared: { owner_name: task.owner_name, member_names: task.member_names, what: "task" },
  };
}

/**
 * A job application's deadline and follow-up date, as all-day items on the
 * calendar (Phase 3 item 1, D4). Only while the application is still in play:
 * a follow-up on one already rejected is nothing to do.
 */
export function applicationOccurrences(applications: Application[], start: string, end: string): EventOccurrence[] {
  const open = new Set(["applied", "screening", "interview", "offer"]);
  const items: EventOccurrence[] = [];
  for (const application of applications) {
    if (!open.has(application.status)) continue;
    const dates: [string | null, "deadline" | "follow_up"][] = [
      [application.deadline, "deadline"], [application.follow_up_on, "follow_up"],
    ];
    for (const [on_date, what] of dates) {
      if (!on_date || on_date < start || on_date > end) continue;
      items.push({
        event_id: `${application.id}-${what}`, on_date,
        title: `${what === "deadline" ? "Deadline" : "Follow up"}: ${application.company}`,
        kind: "deadline", start_time: null, end_time: null, location: null, notes: application.role,
        course_id: null, course_code: null, job_id: null, repeats: false, grade_id: null,
        application: { id: application.id, what, company: application.company, role: application.role },
      });
    }
  }
  return items;
}
