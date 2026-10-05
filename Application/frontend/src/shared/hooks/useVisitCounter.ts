import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../../app/auth/AuthContext";
import { post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { today } from "../utils/dateUtils";
import { isPrompted, takePromptedMarker } from "../utils/promptedSession";

/** The room a path belongs to, as the sidebar names them; null for anything else. */
export function moduleFor(pathname: string): string | null {
  if (pathname === "/") return "dashboard";
  const first = pathname.split("/")[1];
  return ["grades", "calendar", "tasks", "jobs", "budget", "settings"].includes(first) ? first : null;
}

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

/**
 * Tell the server which room is open, once per room per day per tab.
 *
 * Phase 0's analytics (Ideas/overhaul/phase0.md item 4). Only the client knows
 * which page is open -- the dashboard alone reads three modules' data -- so the
 * visit comes from here. Fire and forget: a failed count is never shown to
 * anyone and never retried, because nothing about using the app depends on it.
 */
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
    post(endpoints.usage.visits(userId), prompted ? { module, prompted } : { module }).catch(() => {});
  }, [userId, module]);
}
