import { useEffect, useState } from "react";
import { fetchAgenda, fetchFreeBlocks, fetchWeekLoad } from "../api";
import { EventOccurrence, EXAM_KINDS, FreeBlock, WeekLoad } from "../types";
import { addDays, startOfWeek, today } from "../../../shared/utils/dateUtils";
import { useAuth } from "../../../app/auth/AuthContext";
import { useApiRefreshCount } from "../../../shared/hooks/useApiRefresh";

/** This week's exam and shift counts. */
export interface WeekCounts {
  exams: number;
  shifts: number;
}

/** Count the exams (midterms and finals) and the shifts among occurrences. */
export function countWeek(occurrences: EventOccurrence[]): WeekCounts {
  return {
    exams: occurrences.filter((item) => EXAM_KINDS.includes(item.kind)).length,
    shifts: occurrences.filter((item) => item.kind === "shift").length,
  };
}

/**
 * The dashboard's Monday-to-Sunday week: free blocks, load, and exam and shift counts.
 * `loaded` stays false after a failed read, so a failure never reads as an empty week.
 */
export function useTimeGlance() {
  const { user } = useAuth();
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;
  const [blocks, setBlocks] = useState<FreeBlock[]>([]);
  const [load, setLoad] = useState<WeekLoad | null>(null);
  // Whether the week has been read, successfully. A failed read leaves `load`
  // null exactly as an unanswered one does, and the dashboard's checklist must
  // not take either for "nothing on your week".
  const [loaded, setLoaded] = useState(false);
  // Read apart from the rest: a failure here hides two figures on the phone
  // dashboard and nothing else, so it must not take the week down with it.
  const [counts, setCounts] = useState<WeekCounts | null>(null);
  // Read again when a background refetch finds something new (audit #35).
  const refreshed = useApiRefreshCount();

  useEffect(() => {
    if (!userId) return;

    // Monday to Sunday of the week containing today, so the dashboard and the
    // calendar's week view agree about which week "this week" is.
    const monday = startOfWeek(today());
    const sunday = addDays(monday, 6);

    let cancelled = false;
    fetchAgenda(userId, monday, sunday)
      .then((occurrences) => { if (!cancelled) setCounts(countWeek(occurrences)); })
      .catch(() => { if (!cancelled) setCounts(null); });

    Promise.all([
      fetchFreeBlocks(userId, monday, sunday),
      fetchWeekLoad(userId, monday, sunday),
    ])
      .then(([nextBlocks, nextLoad]) => {
        if (cancelled) return;
        setBlocks(nextBlocks);
        setLoad(nextLoad);
        setLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setBlocks([]);
        setLoad(null);
        setLoaded(false);
      });

    return () => { cancelled = true; };
  }, [userId, refreshed]);

  return { blocks, load, loaded, counts };
}
