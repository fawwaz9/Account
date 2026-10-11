import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";
import { acceptInvite, previewInvite } from "../features/partners/api";
import { AcceptStatus } from "../features/partners/types";
import { TASK_LINK_PREFIX, TaskAcceptStatus, acceptTaskInvite, previewTaskInvite } from "../features/tasks/sharing";
import { EVENT_LINK_PREFIX, EventAcceptStatus, acceptEventInvite, previewEventInvite } from "../features/calender/sharing";
import { shortDate } from "../shared/utils/dateUtils";

const REFUSED: Record<Exclude<AcceptStatus, "accepted">, string> = {
  invalid: "That invite link has expired, been used, or been cancelled. Ask for a new one.",
  own: "That's your own invite link. Send it to the person you want as a partner.",
  already: "You're already partners.",
};

const TASK_REFUSED: Record<Exclude<TaskAcceptStatus, "accepted">, string> = {
  invalid: "That link has expired or been cancelled. Ask for a new one.",
  own: "That's a link to your own task. Send it to the people you're working with.",
  already: "You're already on that task.",
  full: "That task already has as many people on it as it can hold.",
};

const EVENT_REFUSED: Record<Exclude<EventAcceptStatus, "accepted">, string> = {
  invalid: "That link has expired or been cancelled. Ask for a new one.",
  own: "That's a link to your own event. Send it to the people you're meeting.",
  already: "You're already on that event.",
  full: "That event already has as many people on it as it can hold.",
};

type Kind = "partner" | "task" | "event";

/** What the link is for: a partner (the plain fragment, as item 10 sent them), a task or an event. */
function parse(hash: string): { kind: Kind; token: string } {
  const raw = decodeURIComponent(hash.replace(/^#/, ""));
  if (raw.startsWith(TASK_LINK_PREFIX)) return { kind: "task", token: raw.slice(TASK_LINK_PREFIX.length) };
  if (raw.startsWith(EVENT_LINK_PREFIX)) return { kind: "event", token: raw.slice(EVENT_LINK_PREFIX.length) };
  return { kind: "partner", token: raw };
}

/**
 * Opening an invite link (Phase 2 items 10, 9a and 9b; D16, D23, D24). The
 * token is in the fragment (/invite#token, #task:token or #event:token), so it never reaches a
 * server log; it is sent to the API in a request body. Shows who sent it, and
 * for what, then asks before anything happens.
 */
export default function InvitePage() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { kind, token } = parse(location.hash);
  const [inviter, setInviter] = useState<string | null>(null);
  const [taskTitle, setTaskTitle] = useState<string | null>(null);
  const [eventDay, setEventDay] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const invalid = { task: TASK_REFUSED, event: EVENT_REFUSED, partner: REFUSED }[kind].invalid;

  useEffect(() => {
    if (!user) return;
    if (token.length < 16) {
      setProblem(invalid);
      return;
    }
    let cancelled = false;
    let look: Promise<void>;
    if (kind === "task") {
      look = previewTaskInvite(user.id, token).then((found) => {
        if (!cancelled) { setInviter(found.owner_name); setTaskTitle(found.title); }
      });
    } else if (kind === "event") {
      look = previewEventInvite(user.id, token).then((found) => {
        if (!cancelled) { setInviter(found.owner_name); setTaskTitle(found.title); setEventDay(found.starts_on); }
      });
    } else {
      look = previewInvite(user.id, token).then((found) => { if (!cancelled) setInviter(found.inviter_name); });
    }
    look.catch(() => { if (!cancelled) setProblem(invalid); });
    return () => { cancelled = true; };
  }, [user, token, kind, invalid]);

  async function accept() {
    if (!user) return;
    setBusy(true);
    try {
      if (kind === "task") {
        const { status } = await acceptTaskInvite(user.id, token);
        if (status === "accepted") {
          navigate("/tasks", { replace: true });
          return;
        }
        setProblem(TASK_REFUSED[status]);
      } else if (kind === "event") {
        const { status } = await acceptEventInvite(user.id, token);
        if (status === "accepted") {
          navigate("/calendar", { replace: true });
          return;
        }
        setProblem(EVENT_REFUSED[status]);
      } else {
        const { status } = await acceptInvite(user.id, token);
        if (status === "accepted") {
          navigate("/tasks", { replace: true });
          return;
        }
        setProblem(REFUSED[status]);
      }
    } catch {
      setProblem("That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  let offer = null;
  if (inviter && kind === "event") {
    offer = (
      <>
        <p>
          <strong>{inviter}</strong> would like you at <strong>{taskTitle}</strong>
          {eventDay && <> on {shortDate(eventDay)}</>}. It would appear on your calendar with its time, place
          and notes. Nothing else of theirs, and you couldn&rsquo;t change it. {inviter} can take you off, and
          you can leave at any time.
        </p>
        <div className="catalogueActions">
          <button type="button" className="calButton calButtonPrimary" onClick={() => void accept()} disabled={busy}>
            Add it to my calendar
          </button>
          <Link to="/calendar" className="calButton">No thanks</Link>
        </div>
      </>
    );
  } else if (inviter && kind === "task") {
    offer = (
      <>
        <p>
          <strong>{inviter}</strong> would like you on their task <strong>{taskTitle}</strong>. You&rsquo;d see
          its title, notes and due date, and could tick it done for everyone or edit its title and notes.
          Nothing else of theirs. {inviter} can take you off, and you can leave at any time.
        </p>
        <div className="catalogueActions">
          <button type="button" className="calButton calButtonPrimary" onClick={() => void accept()} disabled={busy}>
            Join the task
          </button>
          <Link to="/tasks" className="calButton">No thanks</Link>
        </div>
      </>
    );
  } else if (inviter) {
    offer = (
      <>
        <p>
          <strong>{inviter}</strong> would like you as an accountability partner. You&rsquo;d each see the
          share of the week&rsquo;s tasks the other has done, and their run of good weeks. Never task names,
          grades or money. Either of you can end it at any time.
        </p>
        <div className="catalogueActions">
          <button type="button" className="calButton calButtonPrimary" onClick={() => void accept()} disabled={busy}>
            Become partners
          </button>
          <Link to="/tasks" className="calButton">No thanks</Link>
        </div>
      </>
    );
  }

  return (
    <div className="container invitePage">
      <h1 className="title">An invite</h1>
      {problem ? (
        <p>{problem} <Link to="/tasks">Go to your tasks</Link></p>
      ) : offer ?? (
        <p className="muted" role="status">Checking the invite…</p>
      )}
    </div>
  );
}
