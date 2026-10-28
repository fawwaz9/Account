import { Reminder } from "../types";
import HelpTip from "../../../shared/components/HelpTip";
import { clockTime, dueLabel } from "../../../shared/utils/dateUtils";

/** The reminders now due, and the dismiss handler. */
interface ReminderBannerProps {
  readonly due: Reminder[];
  readonly onDismiss: (reminder: Reminder) => void;
}

/** Due reminders at the top of the page, each staying until it is dismissed. */
export default function ReminderBanner({ due, onDismiss }: ReminderBannerProps) {
  if (due.length === 0) return null;

  return (
    <section className="remBanner" role="status" aria-label="Reminders">
      <div className="remBannerHead">
        <h2 className="remBannerTitle">
          {due.length} {due.length === 1 ? "reminder" : "reminders"}
        </h2>
        <HelpTip label="When reminders fire">
          Only while the app is open. There is no background delivery, so treat these
          as a nudge when you visit rather than something that will reach you.
        </HelpTip>
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
