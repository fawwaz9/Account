import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJobs, fetchShifts } from "../api";
import { Job, ShiftOccurrence } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { addDays, today } from "../../../shared/utils/dateUtils";

/** How far either side of today the shift list reaches. */
const BEHIND_DAYS = 14;
const AHEAD_DAYS = 21;

/**
 * The jobs, and the shifts around today.
 *
 * Both in one hook because the page never wants one without the other: a job
 * with no shifts and a shift with no job are each half an answer.
 */
export function useJobs(includeArchived = false) {
  const { user } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [shifts, setShifts] = useState<ShiftOccurrence[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Every load takes a ticket and only the newest may write state, or toggling
  // archived quickly leaves the slower answer on screen.
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    if (!user) return;

    const ticket = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const from = addDays(today(), -BEHIND_DAYS);
      const to = addDays(today(), AHEAD_DAYS);
      const [nextJobs, nextShifts] = await Promise.all([
        fetchJobs(user.id, includeArchived),
        fetchShifts(user.id, from, to),
      ]);
      if (ticket !== latestRequest.current) return;
      setJobs(nextJobs);
      setShifts(nextShifts);
    } catch (err) {
      if (ticket !== latestRequest.current) return;
      setError(err instanceof Error ? err.message : "Could not load your jobs");
    } finally {
      if (ticket === latestRequest.current) setLoading(false);
    }
  }, [user, includeArchived]);

  useEffect(() => { void load(); }, [load]);

  return { jobs, shifts, loading, error, reload: load };
}
