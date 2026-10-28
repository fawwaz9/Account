import { useCallback, useEffect, useRef, useState } from "react";
import { dismissReminder, fetchDueReminders } from "../api";
import { Reminder } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

/** How often to ask what is due, in ms. */
const POLL_MS = 60_000;

/**
 * Poll every minute for due reminders, notifying once for each one not already pushed.
 * Dismissing drops the banner at once and re-polls if the request fails.
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

/** Best-effort browser notification for each reminder not yet announced here or pushed. */
function announce(rows: Reminder[], seen: Set<string>) {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") {
    return;
  }

  for (const row of rows) {
    if (seen.has(row.id)) continue;
    seen.add(row.id);
    // Already on this person's devices through push; the banner still shows,
    // but a second system notification for the same reminder would not.
    if (row.pushed_at) continue;
    try {
      const body = [row.course_code, row.notes].filter(Boolean).join(" · ");
      // The same tag the pushed notification uses, so if both ever happen
      // the system replaces one with the other instead of stacking them.
      new Notification(row.title, { body: body || undefined, tag: `reminder-${row.id}` });
    } catch {
      // Some browsers throw for a constructed Notification outside a service
      // worker. The banner has already covered it.
    }
  }
}

/** Ask for notification permission (when a first reminder is made); true when granted. */
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
