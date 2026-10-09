import { useEffect, useState } from "react";
import { useAuth } from "../../../app/auth/AuthContext";
import HelpTip from "../../../shared/components/HelpTip";
import { shortDate } from "../../../shared/utils/dateUtils";
import {
  TaskSharing, cancelTaskLink, fetchTaskSharing, makeTaskLink, removeTaskMember, taskInviteLink,
} from "../sharing";
// The Calendar opens the task editor too, without the Tasks page's styles.
import "../../../styles/tasks.css";

interface Props {
  readonly taskId: string;
  /** Called after someone is added or removed, so the row's "with …" updates. */
  readonly onChanged?: () => void;
}

/**
 * Sharing one of your own tasks (Phase 2 item 9a, D23), inside its editor.
 *
 * Whoever opens the link and joins sees the title, notes and due date, can
 * tick it done and edit its text, and can leave. Never its course, grade,
 * timer, priority or tags. Only you change its date, delete it, or change who
 * is on it.
 */
export default function TaskSharingSection({ taskId, onChanged }: Props) {
  const { user } = useAuth();
  const [sharing, setSharing] = useState<TaskSharing | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!user) return;
    try {
      setSharing(await fetchTaskSharing(user.id, taskId));
    } catch {
      setSharing(null);
    }
  }

  useEffect(() => { void load(); }, [user, taskId]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!user || !sharing) return null;
  const userId = user.id;

  async function act(step: () => Promise<unknown>, changed = false) {
    setBusy(true);
    setError(null);
    try {
      await step();
      await load();
      if (changed) onChanged?.();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="taskSharing" aria-label="Share this task">
      <div className="sectionHeading">
        <h3>Share</h3>
        <HelpTip label="What sharing does">
          Anyone who joins through your link sees this task&rsquo;s title, notes and due date. They can tick
          it done for everyone and edit its title and notes. Never its course, grade, timer, priority or tags.
          Only you can change its date, delete it, or change who is on it.
        </HelpTip>
      </div>

      {!sharing.shareable ? (
        <p className="small-text muted">One of a repeat can&rsquo;t be shared. Share a one-off task instead.</p>
      ) : (
        <>
          {sharing.members.length > 0 && (
            <ul className="partnerList">
              {sharing.members.map((member) => (
                <li key={member.id}>
                  <span className="partnerName">{member.name}</span>{" "}
                  {removing === member.id ? (
                    <span className="catalogueActions">
                      <span className="small-text">Take {member.name} off? They lose it at once.</span>
                      <button type="button" className="calButton calButtonDanger" disabled={busy}
                              onClick={() => void act(async () => {
                                await removeTaskMember(userId, taskId, member.id);
                                setRemoving(null);
                              }, true)}>
                        Take off
                      </button>
                      <button type="button" className="calButton" onClick={() => setRemoving(null)}>Keep</button>
                    </span>
                  ) : (
                    <button type="button" className="courseLinkAdd" onClick={() => setRemoving(member.id)}>
                      Take off
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          {link && (
            <div className="inviteLink">
              <p className="small-text">
                Send this link yourself. Anyone with it can join for 7 days, up to {sharing.max_members} people:
              </p>
              <input readOnly value={link} aria-label="Task link" onFocus={(e) => e.target.select()} />
              <button type="button" className="calButton" onClick={() => void copy()}>{copied ? "Copied" : "Copy"}</button>
            </div>
          )}

          {!link && sharing.link && (
            <p className="small-text muted">
              A link is open until {shortDate(sharing.link.expires_at.slice(0, 10))}.{" "}
              <button type="button" className="courseLinkAdd" disabled={busy}
                      onClick={() => void act(() => cancelTaskLink(userId, taskId))}>
                Cancel it
              </button>
            </p>
          )}

          {error && <p className="small-text error" role="alert">{error}</p>}
          <button type="button" className="calButton" disabled={busy}
                  onClick={() => void act(async () => {
                    const made = await makeTaskLink(userId, taskId);
                    setLink(taskInviteLink(made.token));
                    setCopied(false);
                  })}>
            {sharing.link || link ? "Make a new link" : "Share with a link"}
          </button>
          {(sharing.link || link) && (
            <p className="small-text muted">A new link stops the old one working.</p>
          )}
        </>
      )}
    </section>
  );
}
