import { useEffect, useState } from "react";
import { nowIn, ZonedNow } from "../../../shared/utils/zonedNow";

/** The current day and minute in `zone`, updated on each minute boundary. */
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
