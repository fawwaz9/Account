import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import CalenderView from "../features/calender/components/CalenderView";
import WeekView from "../features/calender/components/WeekView";
import EventCard from "../features/calender/components/EventCard";
import EventModal from "../features/calender/components/EventModal";
import SharedOccurrenceCard from "../features/calender/components/SharedOccurrenceCard";
import Modal from "../shared/components/Modal";
import DeleteConfirmModal from "../features/grades/components/DeleteConfirmModal";
import { useCalender } from "../features/calender/hooks/useCalender";
import TimeInsights from "../features/calender/components/TimeInsights";
import TermTimeline from "../features/calender/components/TermTimeline";
import BlackoutsModal from "../features/calender/components/BlackoutsModal";
import {
  deleteEvent,
  fetchEvents,
  skipOccurrence,
} from "../features/calender/api";
import { CalendarEvent, EventOccurrence } from "../features/calender/types";
import { Task } from "../features/tasks/types";
import EditTaskModal from "../features/tasks/components/EditTaskModal";
import { fetchCourses } from "../features/grades/api";
import { Course } from "../features/grades/types";
import { useAuth } from "../app/auth/AuthContext";
import ShiftConflictsPanel from "../features/jobs/components/ShiftConflictsPanel";
import "../styles/jobs.css";
import { addDays, shortDate, today, weekGrid } from "../shared/utils/dateUtils";
import { useShortcut } from "../shared/hooks/useShortcut";
import { useSwipe } from "../shared/hooks/useSwipe";
import { stepNoun, viewName } from "../features/calender/views";
import "../styles/calendar.css";

/**
 * The calendar: month, week, three-day or day view with arrows, swipes and shortcuts, the week's
 * insights, the term timeline, and dialogs for events, tasks, shared items and blackouts.
 */
export default function CalendarPage() {
  const { user } = useAuth();
  const {
    view, setView, phone, views, label, setCursor, step, cursor, days, loading, error, reload,
  } = useCalender();
  // Whichever grid is showing. A sideways swipe on a phone is the arrows by
  // another name, so it calls the same `step` they do.
  const gridRef = useRef<HTMLDivElement>(null);
  useSwipe(gridRef, step, phone);
  const insightWeek = days.length > 0 ? weekGrid(days[0].date) : null;

  const [courses, setCourses] = useState<Course[]>([]);
  const [selected, setSelected] = useState<EventOccurrence | null>(null);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [editing, setEditing] = useState<CalendarEvent | null>(null);
  const [composing, setComposing] = useState(false);
  const [composeDate, setComposeDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  // Bumped with reload so the insights follow an edit.
  const [insightNonce, setInsightNonce] = useState(0);
  const [blackoutsOpen, setBlackoutsOpen] = useState(false);

  // Courses are only needed to label the dropdown in the event form, so they
  // load once here rather than on every month change.
  useEffect(() => {
    if (!user) return;

    let mounted = true;
    fetchCourses(user.id)
      .then((next) => { if (mounted) setCourses(next); })
      .catch(() => { if (mounted) setCourses([]); });

    return () => { mounted = false; };
  }, [user]);

  function openNewEvent(date: string) {
    setEditing(null);
    setComposeDate(date);
    setComposing(true);
  }

  // The same calls the buttons in the header make, so a shortcut can never do
  // something its button would not.
  useShortcut("n", () => openNewEvent(today()));
  useShortcut("ArrowLeft", () => step(-1));
  useShortcut("ArrowRight", () => step(1));
  useShortcut("t", () => setCursor(today()));

  /** A task changed in the editor moves hours around, so the insights refetch. */
  async function handleTaskSaved() {
    await reload();
    setInsightNonce((value) => value + 1);
  }

  /** Edit the whole series: the form is the event, not the occurrence. */
  async function handleEditSeries() {
    if (!user || !selected) return;

    setBusy(true);
    setActionError(null);
    try {
      // The occurrence carries only its event's id, so the series itself has to
      // be fetched before it can be edited.
      const events = await fetchEvents(user.id);
      const event = events.find((candidate) => candidate.id === selected.event_id) ?? null;
      if (!event) throw new Error("That event no longer exists");

      setEditing(event);
      setSelected(null);
      setComposing(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not open the event");
    } finally {
      setBusy(false);
    }
  }

  async function handleSkip() {
    if (!user || !selected) return;

    setBusy(true);
    setActionError(null);
    try {
      await skipOccurrence(user.id, selected.event_id, selected.on_date);
      setSelected(null);
      await reload();
      setInsightNonce((value) => value + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not cancel that date");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!user || !selected) return;
    setConfirmingDelete(false);

    setBusy(true);
    setActionError(null);
    try {
      await deleteEvent(user.id, selected.event_id);
      setSelected(null);
      await reload();
      setInsightNonce((value) => value + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not delete the event");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container">
      <div className="calTopbar">
        <h1 className="title">Calendar</h1>
        <button
          type="button"
          className="calButton calButtonPrimary"
          onClick={() => openNewEvent(today())}
        >
          New event
        </button>
      </div>

      {/* One header for every view: the step buttons mean a month, a week or a
          few days depending on which is showing, so they belong above the
          switch rather than inside any grid. */}
      <header className="calHeader">
        <div className="calNav">
          <button
            type="button"
            className="calButton"
            onClick={() => step(-1)}
            aria-label={`Previous ${stepNoun(view)}`}
          >
            ‹
          </button>
          <h2 className="calMonth">{label}</h2>
          <button
            type="button"
            className="calButton"
            onClick={() => step(1)}
            aria-label={`Next ${stepNoun(view)}`}
          >
            ›
          </button>
        </div>

        <div className="calHeaderActions">
          <button type="button" className="calButton" onClick={() => setCursor(today())}>
            Today
          </button>

          {/* Entered once and applied to every class, rather than cancelling the
              same week on each of six courses. */}
          <button
            type="button"
            className="calButton"
            onClick={() => setBlackoutsOpen(true)}
          >
            Blocked periods
          </button>

          <div className="calViewSwitch" role="group" aria-label="Calendar view">
            {/* A phone offers one and three days in place of the week (views.ts). */}
            {views.map((option) => (
              <button
                key={option}
                type="button"
                className={view === option ? "calViewTab calViewTabActive" : "calViewTab"}
                onClick={() => setView(option)}
                aria-pressed={view === option}
              >
                {viewName(option)}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error && <p className="calError">{error}</p>}
      {/* Phase 2 item 14: a shift that runs into, or crowds, an exam. Silent
          when there is none. */}
      {user && <ShiftConflictsPanel userId={user.id} nonce={insightNonce} />}
      {actionError && <p className="calError">{actionError}</p>}

      <div ref={gridRef}>
        {view === "month" ? (
          <CalenderView
            month={cursor}
            days={days}
            loading={loading}
            onSelectOccurrence={setSelected}
            onSelectTask={setEditingTask}
            onAddOnDay={openNewEvent}
          />
        ) : (
          <WeekView
            days={days}
            loading={loading}
            onSelectOccurrence={setSelected}
            onSelectTask={setEditingTask}
            onAddOnDay={openNewEvent}
          />
        )}
      </div>

      {/* Time-axis views only: the gaps between classes only mean something
          against a time axis, and a month of free blocks is a list nobody
          reads. Always a whole week, the one the first day on screen falls in,
          even in the one- and three-day views: a week's load measured over
          three days would read as a light week. */}
      {view !== "month" && user && insightWeek && (
        <TimeInsights
          userId={user.id}
          weekStart={insightWeek[0]}
          weekEnd={insightWeek[6]}
          horizonEnd={addDays(insightWeek[0], 12 * 7)}
          nonce={insightNonce}
        />
      )}

      {/* Every view. Unlike the free blocks above, the shape of a term does not
          need a time axis to mean something -- and it answers a question the
          month grid raises as readily as the week one. */}
      <TermTimeline courses={courses} />

      {selected && (
        <Modal
          title={`${selected.title} — ${shortDate(selected.on_date)}`}
          onClose={() => setSelected(null)}
        >
          {/* Phase 2 item 9b: someone else's, shared with you. Theirs to
              change, so none of the edit, cancel or delete controls. */}
          {selected.application ? (
            // Phase 3 item 1 (D4): a tracker date. The next step is recorded
            // on the application, so this only points there.
            <div className="calForm">
              <p>
                {selected.application.what === "deadline" ? "Application deadline" : "Follow up"} for{" "}
                <strong>{selected.application.role}</strong> at <strong>{selected.application.company}</strong>.
              </p>
              <div className="calFormActions">
                <button type="button" className="calButton" onClick={() => setSelected(null)}>Close</button>
                <Link to="/jobs/applications" className="calButton calButtonPrimary">Open in Applications</Link>
              </div>
            </div>
          ) : selected.shared && user ? (
            <SharedOccurrenceCard
              userId={user.id}
              occurrence={selected}
              onClose={() => setSelected(null)}
              onLeft={() => { setSelected(null); void reload(); }}
            />
          ) : (
            <EventCard
              occurrence={selected}
              onEdit={handleEditSeries}
              onSkip={handleSkip}
              onDelete={() => setConfirmingDelete(true)}
              onClose={() => setSelected(null)}
              busy={busy}
            />
          )}
        </Modal>
      )}

      {/* The task page's editor, not a second one. A task opened from the
          calendar and the same task opened from its list are the same record,
          and two dialogs for one record is how the two end up offering
          different fields. */}
      <EditTaskModal
        task={editingTask}
        courses={courses}
        onClose={() => setEditingTask(null)}
        onSaved={handleTaskSaved}
      />

      <EventModal
        open={composing}
        event={editing}
        defaultDate={composeDate}
        courses={courses}
        onClose={() => { setComposing(false); setEditing(null); }}
        onSaved={reload}
      />

      {/* `restoreOccurrence` un-skips one occurrence of a repeat; there is no
          undelete for an event, so this is permanent and asks first. */}
      <DeleteConfirmModal
        open={confirmingDelete}
        title="Delete this event?"
        message={
          selected
            ? `"${selected.title}" will be deleted from the calendar. If it repeats, the `
              + `whole series goes, not just this occurrence.`
            : ""
        }
        submitting={busy}
        error={actionError}
        onCancel={() => setConfirmingDelete(false)}
        onConfirm={() => void handleDelete()}
      />

      <BlackoutsModal
        open={blackoutsOpen}
        onClose={() => setBlackoutsOpen(false)}
        onSaved={() => {
          reload();
          setInsightNonce((value) => value + 1);
        }}
      />

    </div>
  );
}
