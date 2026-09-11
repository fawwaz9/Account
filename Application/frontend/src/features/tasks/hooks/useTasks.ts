import { useCallback, useEffect, useRef, useState } from "react";
import { fetchTasks } from "../api";
import { Task } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

interface UseTasksOptions {
  /** Checked-off tasks are archived, so history needs both flags. */
  includeDone?: boolean;
  includeArchived?: boolean;
  courseId?: string;
}

/** The task list, with whatever filter the page is showing. */
export function useTasks({ includeDone, includeArchived, courseId }: UseTasksOptions = {}) {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Same ticket rule as the calendar: toggling "show completed" twice quickly
  // must not leave the earlier answer on screen under the later label.
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
      const next = await fetchTasks(user.id, { includeDone, includeArchived, courseId });
      if (ticket !== latestRequest.current) return;
      setTasks(next);
    } catch (err) {
      if (ticket !== latestRequest.current) return;
      setError(err instanceof Error ? err.message : "Could not load your tasks");
    } finally {
      if (ticket === latestRequest.current) setLoading(false);
    }
  }, [user, includeDone, includeArchived, courseId]);

  useEffect(() => {
    load();
  }, [load]);

  return { tasks, loading, error, reload: load };
}
