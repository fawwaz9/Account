import { useEffect, useState } from "react";
import CalenderView from "../features/calender/components/CalenderView";
import WeekView from "../features/calender/components/WeekView";
import EventCard from "../features/calender/components/EventCard";
import EventModal from "../features/calender/components/EventModal";
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
import { addDays, monthLabel, shortDate, today, weekLabel } from "../shared/utils/dateUtils";
import "../styles/calendar.css";

export default function CalendarPage() {
  const { user } = useAuth();
  const { view, setView, cursor, setCursor, step, days, loading, error, reload } =
    useCalender();

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

      {/* One header for both views: the step buttons mean a month or a week
          depending on which is showing, so they belong above the switch rather
          than inside either grid. */}
      <header className="calHeader">
        <div className="calNav">
          <button
            type="button"
            className="calButton"
            onClick={() => step(-1)}
            aria-label={view === "month" ? "Previous month" : "Previous week"}
          >
            ‹
          </button>
          <h2 className="calMonth">
            {view === "month" ? monthLabel(cursor) : weekLabel(cursor)}
          </h2>
          <button
            type="button"
            className="calButton"
            onClick={() => step(1)}
            aria-label={view === "month" ? "Next month" : "Next week"}
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
            {(["month", "week"] as const).map((option) => (
              <button
                key={option}
                type="button"
                className={view === option ? "calViewTab calViewTabActive" : "calViewTab"}
                onClick={() => setView(option)}
                aria-pressed={view === option}
              >
                {option === "month" ? "Month" : "Week"}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error && <p className="calError">{error}</p>}
      {actionError && <p className="calError">{actionError}</p>}

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
        <>
          <WeekView
            days={days}
            loading={loading}
            onSelectOccurrence={setSelected}
            onSelectTask={setEditingTask}
            onAddOnDay={openNewEvent}
          />

          {/* Week view only: the gaps between classes only mean something
              against a time axis, and a month of free blocks is a list nobody
              reads. */}
          {user && days.length > 0 && (
            <TimeInsights
              userId={user.id}
              weekStart={days[0].date}
              weekEnd={days[days.length - 1].date}
              horizonEnd={addDays(days[0].date, 12 * 7)}
              nonce={insightNonce}
            />
          )}
        </>
      )}

      {/* Both views. Unlike the free blocks above, the shape of a term does not
          need a time axis to mean something -- and it answers a question the
          month grid raises as readily as the week one. */}
      <TermTimeline courses={courses} />

      {selected && (
        <Modal
          title={`${selected.title} — ${shortDate(selected.on_date)}`}
          onClose={() => setSelected(null)}
        >
          <EventCard
            occurrence={selected}
            onEdit={handleEditSeries}
            onSkip={handleSkip}
            onDelete={() => setConfirmingDelete(true)}
            onClose={() => setSelected(null)}
            busy={busy}
          />
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
