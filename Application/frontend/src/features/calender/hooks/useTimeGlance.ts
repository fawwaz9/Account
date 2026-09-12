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
  const [blocks, setBlocks] = useState<FreeBlock[]>([]);
  const [load, setLoad] = useState<WeekLoad | null>(null);

  useEffect(() => {
    if (!user) return;

    // Monday to Sunday of the week containing today, so the dashboard and the
    // calendar's week view agree about which week "this week" is.
    const now = new Date();
    const monday = addDays(isoDate(now), -((now.getDay() + 6) % 7));
    const sunday = addDays(monday, 6);

    let cancelled = false;
    Promise.all([
      fetchFreeBlocks(user.id, monday, sunday),
      fetchWeekLoad(user.id, monday, sunday),
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
  }, [user]);

  return { blocks, load };
}
