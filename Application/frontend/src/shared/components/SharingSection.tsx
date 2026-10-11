import { ReactNode, useEffect, useState } from "react";
import HelpTip from "./HelpTip";
import { shortDate } from "../utils/dateUtils";
// The Calendar opens the editors too, without the Tasks page's styles.
import "../../styles/tasks.css";

/** The owner's view of who is on something of theirs (Phase 2 items 9a, 9b). */
export interface Sharing {
  members: { id: string; name: string; joined_at: string }[];
  link: { expires_at: string } | null;
  shareable: boolean;
  max_members: number;
}

interface Props {
  /** "task" or "event", for the link's label. */
  readonly noun: string;
  readonly load: () => Promise<Sharing>;
  readonly makeLink: () => Promise<{ token: string }>;
  readonly cancelLink: () => Promise<unknown>;
  readonly removeMember: (memberId: string) => Promise<unknown>;
  /** The full link to send, built from a token. */
  readonly linkFor: (token: string) => string;
  /** What joining lets someone do, behind the question mark. */
  readonly help: ReactNode;
  /** Said instead of the controls when this can't be shared. */
  readonly notShareable: string;
  /** Called after someone is taken off, so a "with ..." label elsewhere updates. */
  readonly onChanged?: () => void;
}

/**
 * Sharing something of yours with a link (Phase 2 D23, D24), inside its
 * editor. Saves as you go, apart from the editor's own Save.
 */
export default function SharingSection({
  noun, load, makeLink, cancelLink, removeMember, linkFor, help, notShareable, onChanged,
}: Props) {
  const [sharing, setSharing] = useState<Sharing | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setSharing(await load());
    } catch {
      setSharing(null);
    }
  }

  useEffect(() => { void refresh(); }, [load]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!sharing) return null;

  async function act(step: () => Promise<unknown>, changed = false) {
    setBusy(true);
    setError(null);
    try {
      await step();
      await refresh();
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

  const label = noun.charAt(0).toUpperCase() + noun.slice(1);

  return (
    <section className="taskSharing" aria-label={`Share this ${noun}`}>
      <div className="taskSharingHeading">
        <h3>Share</h3>
        <HelpTip label="What sharing does">{help}</HelpTip>
      </div>

      {!sharing.shareable ? (
        <p className="small-text muted">{notShareable}</p>
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
                                await removeMember(member.id);
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
              <input readOnly value={link} aria-label={`${label} link`} onFocus={(e) => e.target.select()} />
              <button type="button" className="calButton" onClick={() => void copy()}>{copied ? "Copied" : "Copy"}</button>
            </div>
          )}

          {!link && sharing.link && (
            <p className="small-text muted">
              A link is open until {shortDate(sharing.link.expires_at.slice(0, 10))}.{" "}
              <button type="button" className="courseLinkAdd" disabled={busy} onClick={() => void act(cancelLink)}>
                Cancel it
              </button>
            </p>
          )}

          {error && <p className="small-text error" role="alert">{error}</p>}
          <button type="button" className="calButton" disabled={busy}
                  onClick={() => void act(async () => {
                    const made = await makeLink();
                    setLink(linkFor(made.token));
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
