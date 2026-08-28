import { useEffect, useState } from "react";
import { fetchTasks } from "../features/tasks/api";
import { Task } from "../features/tasks/types";
import { useAuth } from "../app/auth/AuthContext";

export default function TasksPage() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      if (!user) return;

      setLoading(true);
      setError(null);

      try {
        const data = await fetchTasks(user.id);
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
  }, [user]);

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