import { FormEvent, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import { TeamListing, updateTeamListing } from "../teams/api";

/** The team, how it's listed now, and what to do after a save. */
interface Props {
  readonly userId: string;
  readonly teamId: string;
  readonly listing: TeamListing;
  readonly onSaved: () => void;
}

/**
 * The captain's campus listing (Phase 3 items 8-9): list the team in the directory and on the
 * campus board, with its level, area, whether it wants players, and a line about it.
 */
export default function TeamListingForm({ userId, teamId, listing, onSaved }: Props) {
  const [listed, setListed] = useState(listing.listed);
  const [level, setLevel] = useState(listing.level ?? "");
  const [area, setArea] = useState(listing.area ?? "");
  const [looking, setLooking] = useState(listing.looking_for_players);
  const [blurb, setBlurb] = useState(listing.blurb ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await updateTeamListing(userId, teamId, {
        listed, level: (level || null) as TeamListing["level"], area: area.trim() || null,
        looking_for_players: looking, blurb: blurb.trim() || null,
      });
      setMessage("Saved.");
      onSaved();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Couldn't save that");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="teamListing" onSubmit={save} aria-label="Campus listing">
      <div className="fitnessCardHead">
        <h3>On campus</h3>
        <HelpTip label="About listing a team">
          A listed team appears in the league directory, where anyone can ask to join, and on the campus
          board ranked by its players&rsquo; points. Only the team&rsquo;s name and these details are shown,
          never a member&rsquo;s name. Both open once 5 teams are listed.
        </HelpTip>
      </div>
      <label className="settingsToggle">
        <input type="checkbox" checked={listed} onChange={(e) => setListed(e.target.checked)} />
        List this team on campus
      </label>
      <div className="teamListingFields">
        <select className="calInput" value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Level">
          <option value="">Any level</option>
          <option value="casual">Casual</option>
          <option value="intermediate">Intermediate</option>
          <option value="competitive">Competitive</option>
        </select>
        <input className="calInput" value={area} maxLength={60} placeholder="Where you play" aria-label="Where you play"
               onChange={(e) => setArea(e.target.value)} />
        <input className="calInput" value={blurb} maxLength={200} placeholder="A line about the team"
               aria-label="A line about the team" onChange={(e) => setBlurb(e.target.value)} />
      </div>
      <label className="settingsToggle">
        <input type="checkbox" checked={looking} onChange={(e) => setLooking(e.target.checked)} />
        Looking for players
      </label>
      <button type="submit" className="calButton" disabled={busy}>Save listing</button>
      {message && <p className="small-text" role="status">{message}</p>}
    </form>
  );
}
