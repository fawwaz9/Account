import { Reminder } from "../types";
import { clockTime, dueLabel } from "../../../shared/utils/dateUtils";

interface ReminderBannerProps {
  readonly due: Reminder[];
  readonly onDismiss: (reminder: Reminder) => void;
}

/**
 * What is due, at the top of the page until it is acknowledged.
 *
 * The reliable half of the delivery: a browser notification needs permission
 * and a tab that is open, this needs neither. It stays until dismissed rather
 * than fading, because a reminder you missed is the failure mode that matters.
 *
 * The line about the app being open is not an apology — it is the honest limit
 * of a design with no scheduler behind it, and saying it is what stops anything
 * important being trusted here.
 */
export default function ReminderBanner({ due, onDismiss }: ReminderBannerProps) {
  if (due.length === 0) return null;

  return (
    <section className="remBanner" role="status" aria-label="Reminders">
      <div className="remBannerHead">
        <h2 className="remBannerTitle">
          {due.length} {due.length === 1 ? "reminder" : "reminders"}
        </h2>
        <span className="small-text muted">These only fire while the app is open</span>
      </div>

      <ul className="remList">
        {due.map((reminder) => (
          <li key={reminder.id} className="remRow">
            <span className="remBody">
              <span className="remTitle">{reminder.title}</span>
              <span className="small-text muted">
                {[
                  dueLabel(reminder.remind_at.slice(0, 10)),
                  clockTime(reminder.remind_at.slice(11, 16)),
                  reminder.course_code,
                  reminder.notes,
                ].filter(Boolean).join(" · ")}
              </span>
            </span>

            <button
              type="button"
              className="remDismiss"
              onClick={() => onDismiss(reminder)}
              aria-label={`Dismiss ${reminder.title}`}
            >
              Got it
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
