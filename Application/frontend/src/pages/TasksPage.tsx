import { useEffect, useState } from "react";
import { fetchTasks } from "../features/tasks/api";
import { Task } from "../features/tasks/types";
import { getOrCreateUserId } from "../services/userService";

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const userId = await getOrCreateUserId();
        const data = await fetchTasks(userId);
        if (mounted) setTasks(data);
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : "Failed to load tasks");
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
      <h1>Tasks</h1>
      <div className="card">
        {loading && <p>Connecting to tasks API...</p>}
        {error && <p className="muted">{error}</p>}
        {!loading && !error && (
          <ul>
            {tasks.map((task) => (
              <li key={task.id}>{task.title}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
