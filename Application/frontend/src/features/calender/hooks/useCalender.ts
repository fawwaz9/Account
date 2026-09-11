import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAgenda } from "../api";
import { EventOccurrence } from "../types";
import { fetchTasks } from "../../tasks/api";
import { Task } from "../../tasks/types";
import { useAuth } from "../../../app/auth/AuthContext";
import { firstOfMonth, monthGrid, today } from "../../../shared/utils/dateUtils";

export interface CalendarDay {
  date: string;
  occurrences: EventOccurrence[];
  tasks: Task[];
}

/**
 * One month of the calendar: events expanded by the API, plus the tasks due in
 * the same window.
 *
 * Two requests rather than one combined endpoint, because a deadline is edited
 * on the task and a lecture is edited on the event -- merging them server-side
 * would create a third shape that belongs to neither and has to be unpicked
 * before anything can be saved.
 */
export function useCalender() {
  const { user } = useAuth();
  const [month, setMonth] = useState(firstOfMonth(today()));
  const [occurrences, setOccurrences] = useState<EventOccurrence[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // The grid runs from the Monday before the 1st to the Sunday after the last,
  // so the window has to cover those overflow days or the first and last rows
  // come back empty.
  const days = monthGrid(month);
  const windowStart = days[0];
  const windowEnd = days[days.length - 1];

  // Every load takes a ticket and only the newest may write state. Stepping the
  // month quickly fires several at once, and without this October resolving
  // after November leaves October's events under November's heading -- the same
  // bug the budget month picker had (audit #12).
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    if (!user) {
      setLoading(false);
      return;
    }

    const ticket = ++latestRequest.current;
    setLoading(true);
    setError(null);

    try {
      const [nextOccurrences, nextTasks] = await Promise.all([
        fetchAgenda(user.id, windowStart, windowEnd),
        fetchTasks(user.id, { start: windowStart, end: windowEnd }),
      ]);
      if (ticket !== latestRequest.current) return;
      setOccurrences(nextOccurrences);
      setTasks(nextTasks);
    } catch (err) {
      if (ticket !== latestRequest.current) return;
      setError(err instanceof Error ? err.message : "Could not load your calendar");
    } finally {
      if (ticket === latestRequest.current) setLoading(false);
    }
  }, [user, windowStart, windowEnd]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    month,
    setMonth,
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

  return days.map((date) => buckets.get(date)!);
}
