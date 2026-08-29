import { useCallback, useEffect, useState } from "react";
import { fetchDashboard } from "../api";
import { UserGradeDashboard } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

/** The cross-course rollup: averages, CGPA, credits, and year summaries. */
export function useDashboard() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<UserGradeDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      setSummary(await fetchDashboard(user.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load your grades");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  return { summary, loading, error, reload: load };
}
