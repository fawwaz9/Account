import { FormEvent, useCallback, useEffect, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import SharingSection from "../../shared/components/SharingSection";
import { shortDate } from "../../shared/utils/dateUtils";
import {
  ClubDetail, ClubSummary, addClubEvent, addClubPoll, addClubPost, cancelClubLink, clubInviteLink, createClub,
  deleteClub, deleteClubEvent, deleteClubMember, deleteClubPoll, deleteClubPost, fetchClub, fetchClubs, leaveClub,
  makeClubLink, voteClubPoll,
} from "./api";

/**
 * "Clubs" on the Fitness page (Phase 3 item 10): the clubs you own or are in, making one, and the
 * chosen club's announcements, polls and events. Only a club's owner posts, asks and adds events.
 */
export default function ClubsSection({ userId }: { readonly userId: string }) {
  const [clubs, setClubs] = useState<ClubSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const found = await fetchClubs(userId);
      setClubs(found);
      setSelected((current) => (current && found.some((c) => c.club_id === current) ? current : null));
    } catch {
      setClubs(null);
    }
  }, [userId]);

  useEffect(() => { void load(); }, [load]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setError(null);
    try {
      const made = await createClub(userId, name.trim(), null);
      setName("");
      await load();
      setSelected(made.club_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't make the club");
    }
  }

  if (!clubs) return null;

  return (
    <section className="clubsSection" aria-label="Clubs">
      <div className="fitnessCardHead">
        <h2>Clubs</h2>
        <HelpTip label="About clubs">
          A club has members who join by your link, announcements, polls with one vote each, and events
          that appear on every member&rsquo;s calendar. Only you post, ask and add events to your own club;
          members see names, never each other&rsquo;s votes.
        </HelpTip>
      </div>
      {error && <p className="calError" role="alert">{error}</p>}
      <div className="clubsGrid">
        <div className="clubsList">
          {clubs.length === 0 && <p className="small-text muted">No clubs yet. Make one, then share its link.</p>}
          <ul>
            {clubs.map((club) => (
              <li key={club.club_id}>
                <button type="button" aria-pressed={selected === club.club_id}
                        className={selected === club.club_id ? "teamCard teamCardActive" : "teamCard"}
                        onClick={() => setSelected(club.club_id)}>
                  <span className="teamCardName">{club.name}</span>
                  <span className="small-text muted">
                    {club.is_owner ? "your club" : `${club.owner_name}'s club`} · {club.member_count}
                    {club.member_count === 1 ? " member" : " members"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <form className="teamsNew" onSubmit={create}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Club name" maxLength={80}
                   aria-label="New club name" />
            <button type="submit" className="calButton calButtonPrimary" disabled={!name.trim()}>New club</button>
          </form>
        </div>
        {selected && (
          <ClubView key={selected} userId={userId} clubId={selected} onChanged={load}
                    onGone={() => { setSelected(null); void load(); }} />
        )}
      </div>
    </section>
  );
}

/** One club: its posts, polls and events, with the owner's controls or a member's vote and leave. */
function ClubView({ userId, clubId, onChanged, onGone }: {
  userId: string;
  clubId: string;
  onChanged: () => Promise<void>;
  onGone: () => void;
}) {
  const [club, setClub] = useState<ClubDetail | null>(null);
  const [post, setPost] = useState("");
  const [question, setQuestion] = useState("");
  const [options, setOptions] = useState("");
  const [closesOn, setClosesOn] = useState("");
  const [eventTitle, setEventTitle] = useState("");
  const [eventDay, setEventDay] = useState("");
  const [eventStart, setEventStart] = useState("");
  const [eventPlace, setEventPlace] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setClub(await fetchClub(userId, clubId));
    } catch {
      setClub(null);
    }
  }, [userId, clubId]);

  useEffect(() => { void load(); }, [load]);

  async function act(step: () => Promise<ClubDetail | unknown>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      const result = await step();
      if (result && typeof result === "object" && "polls" in result) setClub(result as ClubDetail);
      else await load();
      setConfirming(null);
      after?.();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const sharing = useCallback(async () => {
    const detail = await fetchClub(userId, clubId);
    return { members: detail.members ?? [], link: detail.link, shareable: true, max_members: 200 };
  }, [userId, clubId]);

  if (!club) return <p className="muted" role="status">Loading the club…</p>;
  const owner = club.is_owner;

  /** The inline delete pair for one row of the owner's, by a key naming it. */
  function confirmPair(key: string, label: string, remove: () => Promise<unknown>) {
    return confirming === key ? (
      <span className="clubConfirm">
        <button type="button" className="calButton calButtonDanger" disabled={busy}
                onClick={() => void act(remove)}>Yes, delete</button>
        <button type="button" className="calButton" onClick={() => setConfirming(null)}>Keep</button>
      </span>
    ) : (
      <button type="button" className="courseLinkAdd" aria-label={`Delete ${label}`}
              onClick={() => setConfirming(key)}>Delete</button>
    );
  }

  return (
    <section className="teamView clubView" aria-label={club.name}>
      <header className="teamHeader">
        <h3>{club.name}</h3>
        <p className="small-text muted">
          {owner ? "Your club" : `${club.owner_name}'s club`} · {club.member_count}
          {club.member_count === 1 ? " member" : " members"}
          {club.about && ` · ${club.about}`}
        </p>
      </header>
      {error && <p className="calError" role="alert">{error}</p>}

      <div className="clubBlock" aria-label="Announcements">
        <h4>Announcements</h4>
        {owner && (
          <form className="clubForm" onSubmit={(e) => {
            e.preventDefault();
            void act(() => addClubPost(userId, clubId, post.trim()), () => setPost(""));
          }}>
            <textarea className="calInput" rows={2} maxLength={1000} value={post} aria-label="Announcement"
                      placeholder="Tell the club something" onChange={(e) => setPost(e.target.value)} />
            <button type="submit" className="calButton calButtonPrimary" disabled={busy || !post.trim()}>Post</button>
          </form>
        )}
        {club.posts.length === 0 ? <p className="small-text muted">Nothing posted yet.</p> : (
          <ul className="clubList">
            {club.posts.map((p) => (
              <li key={p.post_id}>
                <span>{p.body}</span>
                {owner && confirmPair(`post-${p.post_id}`, "announcement",
                  () => deleteClubPost(userId, clubId, p.post_id))}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="clubBlock" aria-label="Polls">
        <h4>Polls</h4>
        {owner && (
          <form className="clubForm" onSubmit={(e) => {
            e.preventDefault();
            const choices = options.split("\n").map((o) => o.trim()).filter(Boolean);
            void act(() => addClubPoll(userId, clubId, question.trim(), choices, closesOn || null),
              () => { setQuestion(""); setOptions(""); setClosesOn(""); });
          }}>
            <input className="calInput" value={question} maxLength={200} placeholder="Question" aria-label="Question"
                   onChange={(e) => setQuestion(e.target.value)} />
            <textarea className="calInput" rows={3} value={options} aria-label="Choices, one per line"
                      placeholder="Choices, one per line (2 to 6)" onChange={(e) => setOptions(e.target.value)} />
            <input type="date" className="calInput" value={closesOn} aria-label="Last day to vote"
                   onChange={(e) => setClosesOn(e.target.value)} />
            <button type="submit" className="calButton calButtonPrimary" disabled={busy || !question.trim()}>Ask</button>
          </form>
        )}
        {club.polls.length === 0 ? <p className="small-text muted">No polls yet.</p> : (
          <ul className="clubList">
            {club.polls.map((poll) => (
              <li key={poll.poll_id} className="clubPoll">
                <div>
                  <strong>{poll.question}</strong>
                  <span className="small-text muted">
                    {poll.open ? (poll.closes_on ? ` · open until ${shortDate(poll.closes_on)}` : "") : " · closed"}
                  </span>
                  <div className="clubChoices" role="group" aria-label={poll.question}>
                    {poll.options.map((option, index) => (
                      <button key={option} type="button" className="calButton" aria-pressed={poll.my_vote === index}
                              disabled={busy || !poll.open}
                              onClick={() => void act(() => voteClubPoll(userId, clubId, poll.poll_id, index))}>
                        {option} · {poll.counts[index]}
                      </button>
                    ))}
                  </div>
                </div>
                {owner && confirmPair(`poll-${poll.poll_id}`, "poll",
                  () => deleteClubPoll(userId, clubId, poll.poll_id))}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="clubBlock" aria-label="Events">
        <h4>Events</h4>
        {owner && (
          <form className="clubForm clubEventForm" onSubmit={(e) => {
            e.preventDefault();
            void act(() => addClubEvent(userId, clubId, {
              title: eventTitle.trim(), on_date: eventDay, start_time: eventStart || null, end_time: null,
              location: eventPlace.trim() || null,
            }), () => { setEventTitle(""); setEventDay(""); setEventStart(""); setEventPlace(""); });
          }}>
            <input className="calInput" value={eventTitle} maxLength={80} placeholder="What" aria-label="Event"
                   onChange={(e) => setEventTitle(e.target.value)} />
            <input type="date" className="calInput" value={eventDay} aria-label="Event day"
                   onChange={(e) => setEventDay(e.target.value)} />
            <input type="time" className="calInput" value={eventStart} aria-label="Starts at"
                   onChange={(e) => setEventStart(e.target.value)} />
            <input className="calInput" value={eventPlace} maxLength={80} placeholder="Where" aria-label="Where"
                   onChange={(e) => setEventPlace(e.target.value)} />
            <button type="submit" className="calButton calButtonPrimary"
                    disabled={busy || !eventTitle.trim() || !eventDay}>Add</button>
          </form>
        )}
        {club.events.length === 0 ? <p className="small-text muted">No events coming up.</p> : (
          <ul className="clubList">
            {club.events.map((ev) => (
              <li key={ev.event_id}>
                <span>
                  {shortDate(ev.on_date)}{ev.start_time && ` ${ev.start_time.slice(0, 5)}`} · {ev.title}
                  {ev.location && <span className="small-text muted"> · {ev.location}</span>}
                </span>
                {owner && confirmPair(`event-${ev.event_id}`, `event ${ev.title}`,
                  () => deleteClubEvent(userId, clubId, ev.event_id))}
              </li>
            ))}
          </ul>
        )}
      </div>

      {owner ? (
        <>
          <SharingSection
            noun="club"
            load={sharing}
            makeLink={() => makeClubLink(userId, clubId)}
            cancelLink={() => cancelClubLink(userId, clubId)}
            removeMember={(memberId) => deleteClubMember(userId, clubId, memberId)}
            linkFor={clubInviteLink}
            notShareable=""
            onChanged={() => { void load(); void onChanged(); }}
            help={<>
              Anyone who joins through your link sees the club&rsquo;s announcements, polls and events, and can
              vote. Only you post, ask, add events, take someone out, or delete the club.
            </>}
          />
          <div className="catalogueActions">
            {confirming === "club" ? (
              <>
                <span className="small-text">Delete {club.name} and everything in it? This can&rsquo;t be undone.</span>
                <button type="button" className="calButton calButtonDanger" disabled={busy}
                        onClick={() => void act(() => deleteClub(userId, clubId), onGone)}>Yes, delete</button>
                <button type="button" className="calButton" onClick={() => setConfirming(null)}>Keep</button>
              </>
            ) : (
              <button type="button" className="courseLinkAdd" onClick={() => setConfirming("club")}>Delete this club</button>
            )}
          </div>
        </>
      ) : (
        <div className="catalogueActions">
          {confirming === "leave" ? (
            <>
              <span className="small-text">Leave {club.name}? You&rsquo;d need a new link to rejoin.</span>
              <button type="button" className="calButton calButtonDanger" disabled={busy}
                      onClick={() => void act(() => leaveClub(userId, clubId), onGone)}>Leave</button>
              <button type="button" className="calButton" onClick={() => setConfirming(null)}>Stay</button>
            </>
          ) : (
            <button type="button" className="courseLinkAdd" onClick={() => setConfirming("leave")}>Leave this club</button>
          )}
        </div>
      )}
    </section>
  );
}
