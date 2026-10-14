import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../app/auth/AuthContext";
import JobsTabs from "../features/jobs/components/JobsTabs";
import ApplicationModal from "../features/jobs/applications/ApplicationModal";
import ApplicationSankey from "../features/jobs/applications/ApplicationSankey";
import SeasonsModal from "../features/jobs/applications/SeasonsModal";
import { addStep, fetchApplications, fetchApplicationStats, fetchSeasons } from "../features/jobs/applications/api";
import { Application, ApplicationStats, Season, STATUS_LABELS } from "../features/jobs/applications/types";
import { defaultSeason, seasonSpan } from "../features/jobs/applications/seasons";
import { arrange, matches } from "../features/jobs/applications/triage";
import Modal from "../shared/components/Modal";
import { shortDate, today } from "../shared/utils/dateUtils";
import { useShortcut } from "../shared/hooks/useShortcut";
import "../styles/calendar.css";
import "../styles/jobs.css";

/** "All time", in the season picker: no season filter at all. */
const ALL = "all";

/**
 * The job application tracker (Phase 3 item 1), under Jobs.
 *
 * Every application, its status and its history, and your own figures: how
 * many replied, how long replies took, and the Sankey of where they went. All
 * single-user -- nothing here is seen by anyone else, the offers' pay included.
 *
 * The page lists only what needs you (D9); everything else is a search away,
 * or one tap on "Show waiting" / "Show finished".
 */
export default function ApplicationsPage() {
  const { user } = useAuth();
  const userId = user?.id;
  const [applications, setApplications] = useState<Application[]>([]);
  const [stats, setStats] = useState<ApplicationStats | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Application | null>(null);
  const [composing, setComposing] = useState(false);
  const [seasons, setSeasons] = useState<Season[] | null>(null);
  // null until the seasons have loaded and the page has picked one (D7).
  const [seasonId, setSeasonId] = useState<string | null>(null);
  const [managing, setManaging] = useState(false);
  const [query, setQuery] = useState("");
  const [showWaiting, setShowWaiting] = useState(false);
  const [showFinished, setShowFinished] = useState(false);
  const [confirmingAll, setConfirmingAll] = useState(false);
  // "Marking 3 of 12" while marking every quiet one; null otherwise.
  const [marking, setMarking] = useState<{ done: number; of: number } | null>(null);
  const latest = useRef(0);

  const loadSeasons = useCallback(async (pick?: Season) => {
    if (!userId) return;
    try {
      const list = await fetchSeasons(userId);
      setSeasons(list);
      // A season just made or edited is the one you want to see; otherwise
      // open on the season you're in (D7), keeping a choice already made.
      setSeasonId((was) => {
        if (pick) return pick.id;
        if (was && (was === ALL || list.some((season) => season.id === was))) return was;
        return defaultSeason(list, today())?.id ?? ALL;
      });
    } catch {
      // The tracker still works without seasons: show everything.
      setSeasons([]);
      setSeasonId((was) => was ?? ALL);
    }
  }, [userId]);

  useEffect(() => { void loadSeasons(); }, [loadSeasons]);

  const load = useCallback(async () => {
    if (!userId || seasonId === null) return;
    const ticket = ++latest.current;
    const filter = seasonId === ALL ? null : seasonId;
    try {
      const [list, figures] = await Promise.all([
        fetchApplications(userId, filter), fetchApplicationStats(userId, filter),
      ]);
      if (ticket !== latest.current) return;
      setApplications(list);
      setStats(figures);
      setError(null);
      setLoaded(true);
    } catch (err) {
      if (ticket !== latest.current) return;
      setError(err instanceof Error ? err.message : "Could not load your applications");
    }
  }, [userId, seasonId]);

  useEffect(() => { void load(); }, [load]);
  const season = seasons?.find((item) => item.id === seasonId) ?? null;
  useShortcut("n", () => { setEditing(null); setComposing(true); });

  async function markNoReply(application: Application) {
    if (!userId) return;
    try {
      await addStep(userId, application.id, { status: "no_reply", on_date: today(), note: null });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not mark that");
    }
  }

  /**
   * "No reply" on every quiet one, after a confirm. One at a time, so a
   * failure part-way leaves the rest as they were, and says how far it got.
   */
  async function markAllNoReply(quiet: Application[]) {
    if (!userId) return;
    setMarking({ done: 0, of: quiet.length });
    let done = 0;
    let stopped: string | null = null;
    try {
      for (const item of quiet) {
        await addStep(userId, item.id, { status: "no_reply", on_date: today(), note: null });
        done += 1;
        setMarking({ done, of: quiet.length });
      }
    } catch (err) {
      const why = err instanceof Error ? err.message : "something went wrong";
      stopped = `Marked ${done} of ${quiet.length} as no reply, then stopped: ${why}`;
    }
    setMarking(null);
    setConfirmingAll(false);
    // Reload first: a good reload clears the error, and this one must stay.
    await load();
    if (stopped) setError(stopped);
  }

  const { needsYou, quiet, waiting, finished } = useMemo(() => arrange(applications, today()), [applications]);
  const searching = query.trim() !== "";
  const found = useMemo(
    () => applications.filter((item) => matches(item, query)).sort((a, b) => b.applied_on.localeCompare(a.applied_on)),
    [applications, query],
  );
  const openRow = (item: Application) => { setEditing(item); setComposing(true); };

  return (
    <div className="container">
      <div className="calTopbar">
        <h1 className="title">Jobs</h1>
        <button type="button" className="calButton calButtonPrimary"
          onClick={() => { setEditing(null); setComposing(true); }}>
          New application
        </button>
      </div>
      <JobsTabs />

      {/* D7: everything below -- the figures, the Sankey and the lists -- is
          the chosen season's, so no figure ever disagrees with the list. */}
      {seasons !== null && seasonId !== null && (
        <div className="appSeasonBar">
          <label className="calField appSeasonPick">
            <span className="calFieldLabel">Season</span>
            <select className="calInput" value={seasonId} onChange={(e) => setSeasonId(e.target.value)}>
              {seasons.map((item) => (
                <option key={item.id} value={item.id}>{item.name} ({seasonSpan(item)})</option>
              ))}
              <option value={ALL}>All time</option>
            </select>
          </label>
          <button type="button" className="calButton" onClick={() => setManaging(true)}>
            {seasons.length === 0 ? "Add a season" : "Manage seasons"}
          </button>
        </div>
      )}

      {error && <p className="calError" role="alert">{error}</p>}
      {!loaded && !error && <p className="calMuted" role="status">Loading…</p>}

      {loaded && stats && stats.total > 0 && (
        <section className="appFigures" aria-label="Your figures">
          <Figure value={String(stats.total)} label={stats.total === 1 ? "Application" : "Applications"} />
          <Figure value={stats.reply_rate === null ? "–" : `${Math.round(stats.reply_rate * 100)}%`} label="Heard back" />
          <Figure value={stats.median_days_to_reply === null ? "–" : `${stats.median_days_to_reply}d`} label="Typical wait for a reply" />
          <Figure value={String(stats.interviews)} label={stats.interviews === 1 ? "Interview" : "Interviews"} />
          <Figure value={String(stats.offers)} label={stats.offers === 1 ? "Offer" : "Offers"} />
        </section>
      )}

      {loaded && stats && <ApplicationSankey flows={stats.flows} />}

      {loaded && applications.length === 0 && (
        <p className="calMuted">
          {season
            ? `Nothing applied for in ${season.name} (${seasonSpan(season)}) yet.`
            : "No applications yet. Add each one as you send it, and this page tracks where they go."}
        </p>
      )}

      {applications.length > 0 && (
        <label className="calField appSearch">
          <span className="calFieldLabel">Find an application</span>
          <input type="search" className="calInput" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Company, role, location or source" />
        </label>
      )}

      {searching && (
        <section className="appSection" aria-label="Search results">
          <h2>{found.length === 1 ? "1 match" : `${found.length} matches`}</h2>
          {found.length === 0 ? (
            <p className="calMuted">
              Nothing matches “{query.trim()}”{season ? ` in ${season.name}. Try All time in the season picker.` : "."}
            </p>
          ) : (
            <ul className="appList">
              {found.map((item) => (
                <Row key={item.id} application={item} onOpen={() => openRow(item)}
                  onNoReply={() => void markNoReply(item)} />
              ))}
            </ul>
          )}
        </section>
      )}

      {!searching && applications.length > 0 && (
        <>
          <section className="appSection">
            <h2>Needs you</h2>
            {needsYou.length === 0 ? (
              <p className="calMuted">
                {quiet.length > 0 ? "Nothing in play right now, apart from the quiet ones below." : "Nothing needs you right now."}
              </p>
            ) : (
              <ul className="appList">
                {needsYou.map((item) => (
                  <Row key={item.id} application={item} onOpen={() => openRow(item)}
                    onNoReply={() => void markNoReply(item)} />
                ))}
              </ul>
            )}
          </section>

          {quiet.length > 0 && (
            <section className="appSection">
              <div className="appSectionHead">
                <h2>No reply yet?</h2>
                {quiet.length > 1 && (
                  <button type="button" className="calButton" onClick={() => setConfirmingAll(true)}>
                    Mark all {quiet.length} as no reply
                  </button>
                )}
              </div>
              <p className="small-text muted appSectionNote">Nothing heard in 30 days or more.</p>
              <ul className="appList">
                {quiet.map((item) => (
                  <Row key={item.id} application={item} onOpen={() => openRow(item)}
                    onNoReply={() => void markNoReply(item)} asked />
                ))}
              </ul>
            </section>
          )}

          {(waiting.length > 0 || finished.length > 0) && (
            <div className="appReveal">
              {waiting.length > 0 && (
                <button type="button" className="calButton" aria-expanded={showWaiting}
                  onClick={() => setShowWaiting((was) => !was)}>
                  {showWaiting ? "Hide waiting" : `Show waiting (${waiting.length})`}
                </button>
              )}
              {finished.length > 0 && (
                <button type="button" className="calButton" aria-expanded={showFinished}
                  onClick={() => setShowFinished((was) => !was)}>
                  {showFinished ? "Hide finished" : `Show finished (${finished.length})`}
                </button>
              )}
            </div>
          )}

          {showWaiting && waiting.length > 0 && (
            <section className="appSection">
              <h2>Waiting to hear back</h2>
              <ul className="appList">
                {waiting.map((item) => <Row key={item.id} application={item} onOpen={() => openRow(item)} />)}
              </ul>
            </section>
          )}

          {showFinished && finished.length > 0 && (
            <section className="appSection">
              <h2>Finished</h2>
              <ul className="appList">
                {finished.map((item) => <Row key={item.id} application={item} onOpen={() => openRow(item)} />)}
              </ul>
            </section>
          )}
        </>
      )}

      {confirmingAll && (
        <Modal title="Mark all as no reply?" onClose={() => { if (!marking) setConfirmingAll(false); }}>
          <p>
            {quiet.length} applications have had no news in 30 days or more. Each gets a “No reply” step dated
            today. You can remove a step from any of them later.
          </p>
          {marking && <p className="small-text muted" role="status">Marking {marking.done} of {marking.of}…</p>}
          <div className="calFormActions">
            <button type="button" className="calButton" disabled={marking !== null}
              onClick={() => setConfirmingAll(false)}>
              Cancel
            </button>
            <button type="button" className="calButton calButtonPrimary" disabled={marking !== null}
              onClick={() => void markAllNoReply(quiet)}>
              Mark {quiet.length} as no reply
            </button>
          </div>
        </Modal>
      )}

      <SeasonsModal
        open={managing}
        seasons={seasons ?? []}
        onClose={() => setManaging(false)}
        onSaved={(saved) => void loadSeasons(saved)}
      />

      <ApplicationModal
        open={composing}
        application={editing}
        onClose={() => { setComposing(false); setEditing(null); }}
        onSaved={() => void load()}
      />
    </div>
  );
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="appFigure">
      <span className="appFigureValue">{value}</span>
      <span className="appFigureLabel">{label}</span>
    </div>
  );
}

function Row({ application, onOpen, onNoReply, asked = false }: {
  application: Application; onOpen: () => void; onNoReply?: () => void;
  /** Under the "No reply yet?" heading, which already asks. */
  asked?: boolean;
}) {
  return (
    <li className="appRow">
      <button type="button" className="appRowMain" onClick={onOpen}>
        <span className="appRowTitle">{application.company}</span>
        <span className="small-text muted">{application.role}</span>
      </button>
      <span className={`appStatus appStatus-${application.status}`}>{STATUS_LABELS[application.status]}</span>
      <span className="small-text muted appRowDates">
        Applied {shortDate(application.applied_on)}
        {application.deadline && ` · deadline ${shortDate(application.deadline)}`}
        {application.follow_up_on && ` · follow up ${shortDate(application.follow_up_on)}`}
      </span>
      {/* D3: asked, never set on its own. */}
      {application.quiet && onNoReply && (
        <span className="appQuiet">
          {!asked && "No reply yet? "}
          <button type="button" className="calButton" onClick={onNoReply}>Mark no reply</button>
        </span>
      )}
    </li>
  );
}
