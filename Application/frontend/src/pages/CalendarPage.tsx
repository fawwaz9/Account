import { useEffect, useState } from "react";
import { fetchEvents } from "../features/calender/api";
import { CalendarEvent } from "../features/calender/types";
import { getOrCreateUserId } from "../services/userService";

export default function CalendarPage() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const userId = await getOrCreateUserId();
        const data = await fetchEvents(userId);
        if (mounted) setEvents(data);
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : "Failed to load events");
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="container">
      <h1>Calendar</h1>
      <div className="card">
        {loading && <p>Connecting to calendar API...</p>}
        {error && <p className="muted">{error}</p>}
        {!loading && !error && (
          <ul>
            {events.map((event) => (
              <li key={event.id}>{event.title}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
