import { useEffect, useState } from "react";
import { fetchFreeBlocks, fetchWeekLoad } from "../api";
import { addDays, today } from "../../../shared/utils/dateUtils";
import { useAuth } from "../../../app/auth/AuthContext";

export interface WorkloadForecast {
  /** Minutes estimated against open tasks due in the window. */
  estimatedMinutes: number;
  /** Open tasks due in the window. */
  taskCount: number;
  /** Of those, how many carry no estimate -- so the figure reads honestly. */
  unestimatedTasks: number;
  /** Usable free time inside the study window, time already gone excluded. */
  freeMinutes: number;
}

/**
 * The next seven days, today included: what is due against the room to do it.
 *
 * A rolling window rather than the dashboard's Monday-to-Sunday glance, on
 * purpose. On a Saturday "this week" has a day and a half left in it, which is
 * the wrong question for "do I have time for what is coming". The glance keeps
 * its calendar week, so it still agrees with the calendar.
 *
 * `forecast` stays null until both reads succeed; a failure is never shown as
 * "nothing due".
 */
export function useWorkloadForecast() {
  const { user } = useAuth();
  const userId = user?.id;
  const [forecast, setForecast] = useState<WorkloadForecast | null>(null);

  useEffect(() => {
    if (!userId) return;
    const start = today();
    const end = addDays(start, 6);

    let cancelled = false;
    Promise.all([fetchWeekLoad(userId, start, end), fetchFreeBlocks(userId, start, end)])
      .then(([load, blocks]) => {
        if (cancelled) return;
        setForecast({
          estimatedMinutes: load.estimated_minutes,
          taskCount: load.task_count,
          unestimatedTasks: load.unestimated_tasks,
          freeMinutes: blocks.reduce((total, block) => total + block.minutes, 0),
        });
      })
      .catch(() => {
        if (!cancelled) setForecast(null);
      });

    return () => { cancelled = true; };
  }, [userId]);

  return forecast;
}
