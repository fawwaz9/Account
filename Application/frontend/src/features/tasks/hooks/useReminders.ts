import { useCallback, useEffect, useRef, useState } from "react";
import { dismissReminder, fetchDueReminders } from "../api";
import { Reminder } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

/** How often to ask what is due. A minute is finer than any reminder needs. */
const POLL_MS = 60_000;

/**
 * What should be on screen now.
 *
 * The delivery mechanism in full: the app asks, on an interval, while it is
 * open. There is no scheduler and no push, so a reminder cannot reach you with
 * the tab closed — the banner says so, because a notification you half-trust is
 * worse than one you know the limits of.
 *
 * A browser notification is fired as well when permission has been granted, and
 * only once per reminder: `fired_at` is stamped server-side the first time one
 * is returned, and the set of ids already notified is kept here so a re-render
 * cannot repeat it.
 */
export function useReminders() {
  const { user } = useAuth();
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;
  const [due, setDue] = useState<Reminder[]>([]);
  const notified = useRef<Set<string>>(new Set());

  const poll = useCallback(async () => {
    if (!userId) return;

    try {
      const rows = await fetchDueReminders(userId);
      setDue(rows);
      announce(rows, notified.current);
    } catch {
      // A failed poll is not worth surfacing: the next one is a minute away,
      // and an error banner for a background fetch trains people to ignore
      // banners.
    }
  }, [userId]);

  useEffect(() => {
    if (!userId) return;

    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [userId, poll]);

  const dismiss = useCallback(
    async (reminder: Reminder) => {
      if (!userId) return;
      // Removed here first so the banner goes at once rather than at the next
      // poll, which could be a minute away.
      setDue((current) => current.filter((row) => row.id !== reminder.id));
      try {
        await dismissReminder(userId, reminder.id);
      } catch {
        void poll();
      }
    },
    [userId, poll]
  );

  return { due, dismiss, refresh: poll };
}

/**
 * Fire an OS notification for anything not already announced.
 *
 * Best-effort by design. Permission may be denied, the API may be absent, and
 * the in-app banner is the reliable path either way — this only adds reach for
 * the case where the tab is open but not looked at.
 */
function announce(rows: Reminder[], seen: Set<string>) {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") {
    return;
  }

  for (const row of rows) {
    if (seen.has(row.id)) continue;
    seen.add(row.id);
    try {
      const body = [row.course_code, row.notes].filter(Boolean).join(" · ");
      new Notification(row.title, { body: body || undefined, tag: row.id });
    } catch {
      // Some browsers throw for a constructed Notification outside a service
      // worker. The banner has already covered it.
    }
  }
}

/**
 * Ask for permission, at the moment a first reminder is created.
 *
 * Never on page load: a permission prompt with no context attached is the one
 * people dismiss forever, and there is no second chance to ask.
 */
export async function requestNotificationPermission(): Promise<boolean> {
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;

  try {
    return (await Notification.requestPermission()) === "granted";
  } catch {
    return false;
  }
}
