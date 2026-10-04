import { useEffect, useState } from "react";
import { fetchFreeBlocks, fetchWeekLoad } from "../api";
import { FreeBlock, WeekLoad } from "../types";
import { addDays, startOfWeek, today } from "../../../shared/utils/dateUtils";
import { useAuth } from "../../../app/auth/AuthContext";

/**
 * Just what the dashboard shows: this week's room and what it costs.
 *
 * Deliberately lighter than the Calendar page's own fetch, which also pulls the
 * crunch strip — the same split as useBudgetGlance against useBudget.
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

  useEffect(() => {
    if (!userId) return;

    // Monday to Sunday of the week containing today, so the dashboard and the
    // calendar's week view agree about which week "this week" is.
    const monday = startOfWeek(today());
    const sunday = addDays(monday, 6);

    let cancelled = false;
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
  }, [userId]);

  return { blocks, load, loaded };
}
