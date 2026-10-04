import { useEffect, useState } from "react";
import { nowIn, ZonedNow } from "../../../shared/utils/zonedNow";

/**
 * The current day and minute in `zone`, kept current.
 *
 * Ticks on the minute boundary rather than every 60 seconds from mount: a timer
 * started at 10:14:50 would move the line at :50 past each minute, up to most of
 * a minute after the clock in the corner of the screen already had.
 */
export function useNow(zone: string | null | undefined): ZonedNow {
  const [now, setNow] = useState(() => nowIn(zone));

  useEffect(() => {
    setNow(nowIn(zone));
    let interval: ReturnType<typeof setInterval> | undefined;
    const untilNextMinute = 60_000 - (Date.now() % 60_000);
    const first = setTimeout(() => {
      setNow(nowIn(zone));
      interval = setInterval(() => setNow(nowIn(zone)), 60_000);
    }, untilNextMinute);

    return () => {
      clearTimeout(first);
      if (interval !== undefined) clearInterval(interval);
    };
  }, [zone]);

  return now;
}
