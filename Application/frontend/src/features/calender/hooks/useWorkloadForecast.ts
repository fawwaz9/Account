import { useEffect, useState } from "react";
import { fetchFreeBlocks, fetchWeekLoad } from "../api";
import { addDays, today } from "../../../shared/utils/dateUtils";
import { useAuth } from "../../../app/auth/AuthContext";
import { useApiRefreshCount } from "../../../shared/hooks/useApiRefresh";

/** Work due in the next seven days against the free time to do it. */
export interface WorkloadForecast {
  /** Minutes estimated against open tasks due in the window. */
  estimatedMinutes: number;
  /** Open tasks due in the window. */
  taskCount: number;
  /** Of those, how many carry no estimate. */
  unestimatedTasks: number;
  /** Usable free time inside the study window, time already gone excluded. */
  freeMinutes: number;
  /** Actual-over-estimate ratio scaling `estimatedMinutes`; null when not scaled. */
  estimateRatio?: number | null;
  /** The estimates as typed, before any scaling. */
  typedMinutes?: number;
}

/**
 * Estimated work due over the next seven days, today included, against free study time.
 * Null until both reads succeed, so a failure never reads as nothing due.
 */
export function useWorkloadForecast() {
  const { user } = useAuth();
  const userId = user?.id;
  const [forecast, setForecast] = useState<WorkloadForecast | null>(null);
  // Read again when a background refetch finds something new (audit #35).
  const refreshed = useApiRefreshCount();

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
          estimateRatio: load.estimate_ratio ?? null,
          typedMinutes: load.typed_estimated_minutes ?? load.estimated_minutes,
        });
      })
      .catch(() => {
        if (!cancelled) setForecast(null);
      });

    return () => { cancelled = true; };
  }, [userId, refreshed]);

  return forecast;
}
