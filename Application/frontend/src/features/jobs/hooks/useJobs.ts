import { useCallback, useEffect, useRef, useState } from "react";
import { fetchEarnings, fetchJobs, fetchPaycheques, fetchShifts } from "../api";
import { AHEAD_DAYS, UNCONFIRMED_DAYS } from "../shiftOrder";
import { EarningsSummary, Job, Paycheque, ShiftOccurrence } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { addDays, today } from "../../../shared/utils/dateUtils";
import { useApiRefresh } from "../../../shared/hooks/useApiRefresh";


/**
 * Jobs page data: jobs, shifts from 90 days back to 21 ahead, paycheques and earnings.
 * Loaded together; only the newest load may write state.
 */
export function useJobs(includeArchived = false) {
  const { user } = useAuth();
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;
  const [jobs, setJobs] = useState<Job[]>([]);
  const [shifts, setShifts] = useState<ShiftOccurrence[]>([]);
  const [paycheques, setPaycheques] = useState<Paycheque[]>([]);
  const [earnings, setEarnings] = useState<EarningsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Every load takes a ticket and only the newest may write state, or toggling
  // archived quickly leaves the slower answer on screen.
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    if (!userId) return;

    const ticket = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      // Back far enough that a past shift nobody confirmed stays in the list
      // until it is (shiftOrder.ts); the list itself drops confirmed ones
      // after 20 days.
      const from = addDays(today(), -UNCONFIRMED_DAYS);
      const to = addDays(today(), AHEAD_DAYS);
      const [nextJobs, nextShifts, nextCheques, nextEarnings] = await Promise.all([
        fetchJobs(userId, includeArchived),
        fetchShifts(userId, from, to),
        fetchPaycheques(userId),
        fetchEarnings(userId),
      ]);
      if (ticket !== latestRequest.current) return;
      setJobs(nextJobs);
      setShifts(nextShifts);
      setPaycheques(nextCheques);
      setEarnings(nextEarnings);
    } catch (err) {
      if (ticket !== latestRequest.current) return;
      setError(err instanceof Error ? err.message : "Could not load your jobs");
    } finally {
      if (ticket === latestRequest.current) setLoading(false);
    }
  }, [userId, includeArchived]);

  // Catch up when a background refetch finds something new (audit #35).
  useApiRefresh(load);

  useEffect(() => { void load(); }, [load]);

  return { jobs, shifts, paycheques, earnings, loading, error, reload: load };
}
