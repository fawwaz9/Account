import { useEffect, useState } from "react";
import { fetchEvents } from "../features/calender/api";
import { CalendarEvent } from "../features/calender/types";
import { useAuth } from "../app/auth/AuthContext";

export default function CalendarPage() {
  const { user } = useAuth();
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      if (!user) return;

      setLoading(true);
      setError(null);

      try {
        const data = await fetchEvents(user.id);
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
  }, [user]);

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