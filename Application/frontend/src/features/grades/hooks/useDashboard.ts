import { useCallback, useEffect, useState } from "react";
import { fetchDashboard } from "../api";
import { UserGradeDashboard } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

/** The cross-course rollup: averages, CGPA, credits, and year summaries. */
export function useDashboard() {
  const { user } = useAuth();
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;
  const [summary, setSummary] = useState<UserGradeDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!userId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      setSummary(await fetchDashboard(userId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load your grades");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  return { summary, loading, error, reload: load };
}
