import { useEffect, useState } from "react";
import CalenderView from "../features/calender/components/CalenderView";
import EventCard from "../features/calender/components/EventCard";
import EventModal from "../features/calender/components/EventModal";
import Modal from "../shared/components/Modal";
import { useCalender } from "../features/calender/hooks/useCalender";
import {
  deleteEvent,
  fetchEvents,
  skipOccurrence,
} from "../features/calender/api";
import { CalendarEvent, EventOccurrence } from "../features/calender/types";
import { setTaskDone } from "../features/tasks/api";
import { Task } from "../features/tasks/types";
import { fetchCourses } from "../features/grades/api";
import { Course } from "../features/grades/types";
import { useAuth } from "../app/auth/AuthContext";
import { shortDate, today } from "../shared/utils/dateUtils";
import "../styles/calendar.css";

export default function CalendarPage() {
  const { user } = useAuth();
  const { month, setMonth, days, loading, error, reload } = useCalender();

  const [courses, setCourses] = useState<Course[]>([]);
  const [selected, setSelected] = useState<EventOccurrence | null>(null);
  const [editing, setEditing] = useState<CalendarEvent | null>(null);
  const [composing, setComposing] = useState(false);
  const [composeDate, setComposeDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

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

  async function handleToggleTask(task: Task) {
    if (!user) return;

    setBusy(true);
    setActionError(null);
    try {
      await setTaskDone(user.id, task.id, !task.done);
      await reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not update the task");
    } finally {
      setBusy(false);
    }
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
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not cancel that date");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!user || !selected) return;

    setBusy(true);
    setActionError(null);
    try {
      await deleteEvent(user.id, selected.event_id);
      setSelected(null);
      await reload();
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

      {error && <p className="calError">{error}</p>}
      {actionError && <p className="calError">{actionError}</p>}

      <CalenderView
        month={month}
        days={days}
        loading={loading}
        onMonthChange={setMonth}
        onSelectOccurrence={setSelected}
        onToggleTask={handleToggleTask}
        onAddOnDay={openNewEvent}
      />

      {selected && (
        <Modal
          title={`${selected.title} — ${shortDate(selected.on_date)}`}
          onClose={() => setSelected(null)}
        >
          <EventCard
            occurrence={selected}
            onEdit={handleEditSeries}
            onSkip={handleSkip}
            onDelete={handleDelete}
            busy={busy}
          />
        </Modal>
      )}

      <EventModal
        open={composing}
        event={editing}
        defaultDate={composeDate}
        courses={courses}
        onClose={() => { setComposing(false); setEditing(null); }}
        onSaved={reload}
      />
    </div>
  );
}
