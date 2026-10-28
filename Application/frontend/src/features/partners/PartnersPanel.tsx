import { useEffect, useState } from "react";
import { createInvite, endPartnership, fetchPartners, inviteLink, revokeInvite } from "./api";
import { Figure, Partners } from "./types";
import HelpTip from "../../shared/components/HelpTip";
import { shortDate } from "../../shared/utils/dateUtils";

/** A completion figure in words: this week's percent done and the good-week streak. */
export function figureWords(figure: Figure) {
  const week = figure.week_percent === null ? "nothing due this week" : `${Math.round(figure.week_percent)}% of this week's tasks done`;
  const streak = figure.streak_weeks > 0
    ? ` · ${figure.streak_weeks} good ${figure.streak_weeks === 1 ? "week" : "weeks"} in a row`
    : "";
  return `${week}${streak}`;
}

/** Props for the partners panel. */
interface Props {
  readonly userId: string;
}

/**
 * Accountability partners: your figure, theirs, invite links and ending a partnership.
 * Partners see completion only, never a task's name, a grade or money.
 */
export default function PartnersPanel({ userId }: Props) {
  const [data, setData] = useState<Partners | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [ending, setEnding] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setData(await fetchPartners(userId));
    } catch {
      setData(null);
    }
  }

  useEffect(() => { void load(); }, [userId]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!data) return null;

  async function act(step: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await step();
      await load();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function invite() {
    await act(async () => {
      const made = await createInvite(userId);
      setLink(inviteLink(made.token));
      setCopied(false);
    });
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
    <section className="partnersPanel" aria-label="Accountability partners">
      <div className="sectionHeading">
        <h2>Partners</h2>
        <HelpTip label="What a partner sees">
          The share of this week&rsquo;s tasks you have done, and how many weeks in a row you have
          done 80% or more. Never a task&rsquo;s name, a grade or money. Either of you can end it.
        </HelpTip>
      </div>

      <p className="small-text">What partners see of you: {figureWords(data.mine)}.</p>

      {data.partners.length > 0 && (
        <ul className="partnerList">
          {data.partners.map((partner) => (
            <li key={partner.partner_id}>
              <span className="partnerName">{partner.name}</span>{" "}
              <span className="small-text">
                {partner.figure
                  ? `${figureWords(partner.figure)}${partner.figure.figure_on ? ` · as of ${shortDate(partner.figure.figure_on)}` : ""}`
                  : "hasn't opened the app since you became partners"}
              </span>
              {ending === partner.partner_id ? (
                <span className="catalogueActions">
                  <span className="small-text">End it? {partner.name} will see it has ended.</span>
                  <button type="button" className="calButton calButtonDanger" disabled={busy}
                          onClick={() => void act(async () => { await endPartnership(userId, partner.partner_id); setEnding(null); })}>
                    End partnership
                  </button>
                  <button type="button" className="calButton" onClick={() => setEnding(null)}>Keep</button>
                </span>
              ) : (
                <button type="button" className="courseLinkAdd" onClick={() => setEnding(partner.partner_id)}>
                  End
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {link && (
        <div className="inviteLink">
          <p className="small-text">Send this link yourself. It works once, for 7 days:</p>
          <input readOnly value={link} aria-label="Invite link" onFocus={(e) => e.target.select()} />
          <button type="button" className="calButton" onClick={() => void copy()}>{copied ? "Copied" : "Copy"}</button>
        </div>
      )}

      {data.invites.length > 0 && (
        <ul className="small-text muted partnerInvites">
          {data.invites.map((open) => (
            <li key={open.id}>
              A link you sent, open until {shortDate(open.expires_at.slice(0, 10))}{" "}
              <button type="button" className="courseLinkAdd" disabled={busy}
                      onClick={() => void act(() => revokeInvite(userId, open.id))}>
                Cancel it
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="small-text error" role="alert">{error}</p>}
      <button type="button" className="calButton" onClick={() => void invite()} disabled={busy}>
        Invite a partner
      </button>
    </section>
  );
}
