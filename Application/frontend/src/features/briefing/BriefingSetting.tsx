import { useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import { put } from "../../services/apiClient";
import { useAuth } from "../../app/auth/AuthContext";

/** Whose briefing, and the hour it goes out now (null is off). */
interface BriefingSettingProps {
  readonly userId: string;
  readonly hour: number | null;
}

/** The hours offered: early morning to evening, which is when a day's plan is read. */
const HOURS = [5, 6, 7, 8, 9, 10, 11, 12, 17, 18, 19, 20, 21];

/** 7 as "7am", 17 as "5pm". */
export function hourLabel(hour: number): string {
  const suffix = hour < 12 ? "am" : "pm";
  return `${hour % 12 === 0 ? 12 : hour % 12}${suffix}`;
}

/**
 * The daily briefing push (Phase 4 item 6, D13): the Today card's lines, sent at an
 * hour you pick, once a day, to devices with notifications on. Off until chosen.
 */
export default function BriefingSetting({ userId, hour }: BriefingSettingProps) {
  const { refreshUser } = useAuth();
  const [value, setValue] = useState<number | null>(hour);
  const [message, setMessage] = useState<string | null>(null);

  async function choose(next: number | null) {
    const before = value;
    setValue(next);
    setMessage(null);
    try {
      await put(`briefing/${userId}/schedule`, { hour: next });
      await refreshUser();
      setMessage(next === null ? "Off." : `Every day at ${hourLabel(next)}, on devices with notifications on.`);
    } catch {
      setValue(before);
      setMessage("Couldn't save that. Try again in a moment.");
    }
  }

  return (
    <div className="settingsRow">
      <span className="settingsLabel">
        Daily briefing{" "}
        <HelpTip label="What the daily briefing is">
          Today&apos;s calendar, work due, exams coming up, deadlines at risk and free time, as a notification
          once a day. The same lines as the Today card on the dashboard. No money.
        </HelpTip>
      </span>
      <span className="notificationControls">
        <select
          className="briefingSelect"
          value={value === null ? "off" : String(value)}
          onChange={(e) => void choose(e.target.value === "off" ? null : Number(e.target.value))}
          aria-label="When the daily briefing goes out"
        >
          <option value="off">Off</option>
          {HOURS.map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
        </select>
        {message && <span className="small-text" role="status">{message}</span>}
      </span>
    </div>
  );
}
