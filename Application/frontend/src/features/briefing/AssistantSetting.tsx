import { useEffect, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import { buildUrl } from "../../services/apiClient";
import {
  AssistantTokenStatus, fetchAssistantToken, makeAssistantToken, revokeAssistantToken,
} from "./assistantApi";

/** Whose token. */
interface AssistantSettingProps {
  readonly userId: string;
}

/**
 * BYOAI in Settings (Phase 4 item 7, D4): off until you make a token; shown once, with
 * where to point your assistant; revocable at once. The token reads your daily briefing
 * and nothing else, and the briefing carries no money (D8).
 */
export default function AssistantSetting({ userId }: AssistantSettingProps) {
  const [status, setStatus] = useState<AssistantTokenStatus | null>(null);
  const [fresh, setFresh] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAssistantToken(userId)
      .then((next) => { if (!cancelled) setStatus(next); })
      .catch(() => { if (!cancelled) setMessage("Couldn't check. Try again in a moment."); });
    return () => { cancelled = true; };
  }, [userId]);

  async function make() {
    if (status?.enabled && !window.confirm("Make a new token? The old one stops working at once.")) return;
    setBusy(true);
    setMessage(null);
    try {
      const made = await makeAssistantToken(userId);
      setFresh(made.token);
      setStatus({ enabled: true, prefix: made.prefix, created_at: made.created_at, last_used_at: null });
    } catch {
      setMessage("Couldn't make a token. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    setBusy(true);
    setMessage(null);
    try {
      await revokeAssistantToken(userId);
      setFresh(null);
      setStatus({ enabled: false, prefix: null, created_at: null, last_used_at: null });
      setMessage("Off. The token no longer works.");
    } catch {
      setMessage("Couldn't turn it off. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setMessage("Copied.");
    } catch {
      setMessage("Select the token and copy it by hand.");
    }
  }

  return (
    <div className="settingsRow assistantSetting">
      <span className="settingsLabel">
        Your own assistant{" "}
        <HelpTip label="What letting your assistant in means">
          Your assistant (Claude, ChatGPT or another) can read your daily briefing: today&apos;s calendar, work due,
          exams, deadlines at risk and free time. Nothing else, and no money. The token is shown once; turning
          it off stops it at once.
        </HelpTip>
      </span>
      <span className="assistantControls">
        {status === null && !message && <span className="small-text muted" role="status">Checking…</span>}
        {status && !status.enabled && (
          <button type="button" className="buttons" onClick={make} disabled={busy}>Let my assistant read my briefing</button>
        )}
        {status?.enabled && (
          <>
            <span className="settingsBadge">On</span>
            <span className="small-text muted">
              {status.prefix}…{status.last_used_at ? ` · last read ${new Date(status.last_used_at).toLocaleString()}` : " · not used yet"}
            </span>
            <button type="button" className="buttons" onClick={make} disabled={busy}>New token</button>
            <button type="button" className="buttons" onClick={revoke} disabled={busy}>Turn off</button>
          </>
        )}
        {message && <span className="small-text" role="status">{message}</span>}
      </span>

      {fresh && (
        <div className="assistantFresh" role="note">
          <p className="small-text"><strong>Copy this now: it won&apos;t be shown again.</strong></p>
          <code className="assistantToken">{fresh}</code>
          <button type="button" className="buttons" onClick={() => void copy(fresh)}>Copy</button>
          <p className="small-text muted">
            For an assistant that speaks MCP, add a server at <code>{buildUrl("assistant/mcp")}</code> with the
            header <code>Authorization: Bearer</code> and the token. Anything else can read{" "}
            <code>{buildUrl("assistant/digest")}</code> with the same header.
          </p>
        </div>
      )}
    </div>
  );
}
