import { useEffect, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import {
  needsHomeScreen,
  PermissionRefused,
  pushStatus,
  PushStatus,
  pushSupported,
  sendTestPush,
  thisDeviceIsOn,
  turnOff,
  turnOn,
} from "./push";

type Busy = "on" | "off" | "test" | null;

/**
 * "Notifications on this device", in Settings → Account.
 *
 * Every press says what happened: the button is disabled with its own wording
 * while it works, and the result -- on, off, sent, or why not -- appears next
 * to it. The cases that must be read *before* pressing (an iPhone tab, a
 * browser without push, a server not set up yet) replace the button rather
 * than letting it fail.
 */
export default function NotificationsSetting({ userId }: { readonly userId: string }) {
  const [status, setStatus] = useState<PushStatus | null>(null);
  const [on, setOn] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([pushStatus(userId), thisDeviceIsOn()])
      .then(([next, here]) => {
        if (cancelled) return;
        setStatus(next);
        setOn(here);
      })
      .catch(() => {
        if (!cancelled) setStatus({ available: false, public_key: null, devices: 0 });
      });
    return () => { cancelled = true; };
  }, [userId]);

  async function enable() {
    if (!status?.public_key) return;
    setBusy("on");
    setMessage(null);
    try {
      await turnOn(userId, status.public_key);
      setOn(true);
      setMessage("On. Reminders will reach this device even with the app closed.");
    } catch (err) {
      setMessage(err instanceof PermissionRefused
        ? "Your browser is blocking notifications for this site. Allow them in its site settings, then try again."
        : "Couldn't turn notifications on. Try again in a moment.");
    } finally {
      setBusy(null);
    }
  }

  async function disable() {
    setBusy("off");
    setMessage(null);
    try {
      await turnOff(userId);
      setOn(false);
      setMessage("Off for this device.");
    } catch {
      setMessage("Couldn't turn notifications off. Try again in a moment.");
    } finally {
      setBusy(null);
    }
  }

  async function test() {
    setBusy("test");
    setMessage(null);
    try {
      const { sent } = await sendTestPush(userId);
      setMessage(sent > 0 ? "Sent. It should arrive within a few seconds." : "No device accepted it.");
    } catch {
      setMessage("Couldn't send a test notification.");
    } finally {
      setBusy(null);
    }
  }

  let control: React.ReactNode;
  if (status === null || on === null) {
    control = <span className="small-text muted" role="status">Checking…</span>;
  } else if (needsHomeScreen()) {
    control = (
      <span className="small-text">
        On iPhone, add Account to your Home Screen first (Share, then Add to Home Screen) and
        turn this on from there.
      </span>
    );
  } else if (!pushSupported()) {
    control = <span className="small-text">This browser can't receive notifications.</span>;
  } else if (!status.available) {
    control = <span className="small-text">Not set up on the server yet.</span>;
  } else if (on) {
    control = (
      <span className="notificationControls">
        <span className="settingsBadge">On</span>
        <button type="button" className="buttons" onClick={test} disabled={busy !== null}>
          {busy === "test" ? "Sending…" : "Send a test"}
        </button>
        <button type="button" className="buttons" onClick={disable} disabled={busy !== null}>
          {busy === "off" ? "Turning off…" : "Turn off"}
        </button>
      </span>
    );
  } else {
    control = (
      <button type="button" className="buttons" onClick={enable} disabled={busy !== null}>
        {busy === "on" ? "Turning on…" : "Turn on for this device"}
      </button>
    );
  }

  return (
    <div className="settingsRow">
      <span className="settingsLabel">
        Notifications{" "}
        <HelpTip label="About notifications">
          Reminders arrive on this device at their time, even when the app is closed. Each
          device is turned on separately, and signing out turns this one off.
        </HelpTip>
      </span>
      <span className="notificationSetting">
        {control}
        {message && <span className="small-text" role="status">{message}</span>}
      </span>
    </div>
  );
}
