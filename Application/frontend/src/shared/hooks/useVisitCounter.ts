import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../../app/auth/AuthContext";
import { post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { today } from "../utils/dateUtils";
import { isPrompted, takePromptedMarker } from "../utils/promptedSession";

/** The usage-analytics room for a path, or null for paths outside the counted rooms. */
export function moduleFor(pathname: string): string | null {
  if (pathname === "/") return "dashboard";
  const first = pathname.split("/")[1];
  return ["grades", "calendar", "tasks", "jobs", "budget", "settings"].includes(first) ? first : null;
}

/** True if this tab already sent `key`; otherwise marks it sent. Unusable storage counts again. */
function alreadyCounted(key: string): boolean {
  try {
    if (window.sessionStorage.getItem(key)) return true;
    window.sessionStorage.setItem(key, "1");
    return false;
  } catch {
    // Storage refused: count it. Overcounting a visit is harmless.
    return false;
  }
}

/** Report the open room to the usage endpoint once per room, day and tab; fire and forget. */
export function useVisitCounter() {
  const { pathname } = useLocation();
  const userId = useAuth().user?.id;
  const module = moduleFor(pathname);

  useEffect(() => {
    takePromptedMarker();
    if (!userId || !module) return;
    // Prompted and unprompted are counted apart, so an unprompted visit later
    // the same day still counts after a notification brought you in earlier.
    const prompted = isPrompted();
    const key = `account.visit.${userId}.${today()}.${module}${prompted ? ".prompted" : ""}`;
    if (alreadyCounted(key)) return;
    // Leaves the GET cache alone: nothing on screen reads a visit back, and
    // this runs on every page, so clearing would empty the cache each time.
    post(endpoints.usage.visits(userId), prompted ? { module, prompted } : { module }, { keepCache: true })
      .catch(() => {});
  }, [userId, module]);
}
