import { useEffect, useState } from "react";
import { fetchFreeBlocks, fetchWeekLoad } from "../api";
import { FreeBlock, WeekLoad } from "../types";
import { addDays, isoDate } from "../../../shared/utils/dateUtils";
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

  useEffect(() => {
    if (!userId) return;

    // Monday to Sunday of the week containing today, so the dashboard and the
    // calendar's week view agree about which week "this week" is.
    const now = new Date();
    const monday = addDays(isoDate(now), -((now.getDay() + 6) % 7));
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
      })
      .catch(() => {
        if (cancelled) return;
        setBlocks([]);
        setLoad(null);
      });

    return () => { cancelled = true; };
  }, [userId]);

  return { blocks, load };
}
