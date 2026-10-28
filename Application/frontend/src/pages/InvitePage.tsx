import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";
import { acceptInvite, previewInvite } from "../features/partners/api";
import { AcceptStatus } from "../features/partners/types";
import { TASK_LINK_PREFIX, TaskAcceptStatus, acceptTaskInvite, previewTaskInvite } from "../features/tasks/sharing";
import { EVENT_LINK_PREFIX, EventAcceptStatus, acceptEventInvite, previewEventInvite } from "../features/calender/sharing";
import { shortDate } from "../shared/utils/dateUtils";
import { TEAM_LINK_PREFIX, TeamAcceptStatus, acceptTeamInvite, previewTeamInvite } from "../features/teams/api";
import { CLUB_LINK_PREFIX, ClubAcceptStatus, acceptClubInvite, previewClubInvite } from "../features/clubs/api";

/** Why a partner invite was refused, by status, phrased as what to do. */
const REFUSED: Record<Exclude<AcceptStatus, "accepted">, string> = {
  invalid: "That invite link has expired, been used, or been cancelled. Ask for a new one.",
  own: "That's your own invite link. Send it to the person you want as a partner.",
  already: "You're already partners.",
};

/** Why a shared-task link was refused, by status. */
const TASK_REFUSED: Record<Exclude<TaskAcceptStatus, "accepted">, string> = {
  invalid: "That link has expired or been cancelled. Ask for a new one.",
  own: "That's a link to your own task. Send it to the people you're working with.",
  already: "You're already on that task.",
  full: "That task already has as many people on it as it can hold.",
};

/** Why a shared-event link was refused, by status. */
const EVENT_REFUSED: Record<Exclude<EventAcceptStatus, "accepted">, string> = {
  invalid: "That link has expired or been cancelled. Ask for a new one.",
  own: "That's a link to your own event. Send it to the people you're meeting.",
  already: "You're already on that event.",
  full: "That event already has as many people on it as it can hold.",
};

/** Why a team link was refused, by status. */
const TEAM_REFUSED: Record<Exclude<TeamAcceptStatus, "accepted">, string> = {
  invalid: "That link has expired or been cancelled. Ask for a new one.",
  own: "That's a link to your own team. Send it to your teammates.",
  already: "You're already on that team.",
  full: "That team already has as many players as it can hold.",
};

/** Why a club link was refused, by status (Phase 3 item 10). */
const CLUB_REFUSED: Record<Exclude<ClubAcceptStatus, "accepted">, string> = {
  invalid: "That link has expired or been cancelled. Ask for a new one.",
  own: "That's a link to your own club. Send it to the people you'd like in it.",
  already: "You're already in that club.",
  full: "That club already has as many members as it can hold.",
};

/** What an invite link is for. */
type Kind = "partner" | "task" | "event" | "team" | "club";

/** Kind and token from the fragment: a task, event, team or club prefix, else a partner token. */
function parse(hash: string): { kind: Kind; token: string } {
  const raw = decodeURIComponent(hash.replace(/^#/, ""));
  if (raw.startsWith(TASK_LINK_PREFIX)) return { kind: "task", token: raw.slice(TASK_LINK_PREFIX.length) };
  if (raw.startsWith(EVENT_LINK_PREFIX)) return { kind: "event", token: raw.slice(EVENT_LINK_PREFIX.length) };
  if (raw.startsWith(TEAM_LINK_PREFIX)) return { kind: "team", token: raw.slice(TEAM_LINK_PREFIX.length) };
  if (raw.startsWith(CLUB_LINK_PREFIX)) return { kind: "club", token: raw.slice(CLUB_LINK_PREFIX.length) };
  return { kind: "partner", token: raw };
}

/**
 * Open an invite link: show who sent it and for what, then accept on a press.
 * The token rides in the fragment and goes to the API only in a request body.
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
  const invalid = {
    task: TASK_REFUSED, event: EVENT_REFUSED, team: TEAM_REFUSED, club: CLUB_REFUSED, partner: REFUSED,
  }[kind].invalid;

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
    } else if (kind === "team") {
      look = previewTeamInvite(user.id, token).then((found) => {
        if (!cancelled) { setInviter(found.captain_name); setTaskTitle(found.team_name); setEventDay(found.sport); }
      });
    } else if (kind === "club") {
      look = previewClubInvite(user.id, token).then((found) => {
        if (!cancelled) { setInviter(found.owner_name); setTaskTitle(found.club_name); }
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
      } else if (kind === "team") {
        const { status } = await acceptTeamInvite(user.id, token);
        if (status === "accepted") {
          navigate("/fitness", { replace: true });
          return;
        }
        setProblem(TEAM_REFUSED[status]);
      } else if (kind === "club") {
        const { status } = await acceptClubInvite(user.id, token);
        if (status === "accepted") {
          navigate("/fitness", { replace: true });
          return;
        }
        setProblem(CLUB_REFUSED[status]);
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
  if (inviter && kind === "team") {
    offer = (
      <>
        <p>
          <strong>{inviter}</strong> would like you on <strong>{taskTitle}</strong>
          {eventDay && <>, their {eventDay} team</>}. You&rsquo;d see the team&rsquo;s roster and games, and could
          record, confirm or dispute a score. Nothing else of theirs. {inviter} can take you off, and you can
          leave at any time.
        </p>
        <div className="catalogueActions">
          <button type="button" className="calButton calButtonPrimary" onClick={() => void accept()} disabled={busy}>
            Join the team
          </button>
          <Link to="/fitness" className="calButton">No thanks</Link>
        </div>
      </>
    );
  } else if (inviter && kind === "club") {
    offer = (
      <>
        <p>
          <strong>{inviter}</strong> would like you in <strong>{taskTitle}</strong>. You&rsquo;d see its
          announcements, polls and events, and its events would appear on your calendar. Your vote in a poll
          is counted with no name. {inviter} can take you out, and you can leave at any time.
        </p>
        <div className="catalogueActions">
          <button type="button" className="calButton calButtonPrimary" onClick={() => void accept()} disabled={busy}>
            Join the club
          </button>
          <Link to="/fitness" className="calButton">No thanks</Link>
        </div>
      </>
    );
  } else if (inviter && kind === "event") {
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
