import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRepeating, fetchTasks, runRepeating } from "../api";
import { RecurringTask, Task } from "../types";
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
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;
  const [tasks, setTasks] = useState<Task[]>([]);
  const [repeating, setRepeating] = useState<RecurringTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Same ticket rule as the calendar: toggling "show completed" twice quickly
  // must not leave the earlier answer on screen under the later label.
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    if (!userId) {
      setLoading(false);
      return;
    }

    const ticket = ++latestRequest.current;
    setLoading(true);
    setError(null);

    try {
      // Any repeat whose turn has come is written before anything is read, or a
      // chore due today would not appear until some later page load. Idempotent
      // on (rule, due date), so this writes nothing twice. Failures are
      // swallowed deliberately: not being able to materialise must not stop the
      // list the student already has from rendering.
      await runRepeating(userId).catch(() => undefined);
      if (ticket !== latestRequest.current) return;

      const [next, nextRepeating] = await Promise.all([
        fetchTasks(userId, { includeDone, includeArchived, courseId }),
        fetchRepeating(userId),
      ]);
      if (ticket !== latestRequest.current) return;
      setTasks(next);
      setRepeating(nextRepeating);
    } catch (err) {
      if (ticket !== latestRequest.current) return;
      setError(err instanceof Error ? err.message : "Could not load your tasks");
    } finally {
      if (ticket === latestRequest.current) setLoading(false);
    }
  }, [userId, includeDone, includeArchived, courseId]);

  useEffect(() => {
    load();
  }, [load]);

  return { tasks, repeating, loading, error, reload: load };
}
