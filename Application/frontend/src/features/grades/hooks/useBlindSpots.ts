import { useCallback, useEffect, useState } from "react";
import { fetchBlindSpots } from "../api";
import { CategoryBlindSpot } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { useApiRefresh } from "../../../shared/hooks/useApiRefresh";

/** Categories trailing the student's own average across courses; a failed load reads as none. */
export function useBlindSpots() {
  const { user } = useAuth();
  const [spots, setSpots] = useState<CategoryBlindSpot[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!user) {
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      setSpots(await fetchBlindSpots(user.id));
    } catch {
      setSpots([]);
    } finally {
      setLoading(false);
    }
  }, [user]);

  // Catch up when a background refetch finds something new (audit #35).
  useApiRefresh(load);

  useEffect(() => {
    load();
  }, [load]);

  return { spots, loading, reload: load };
}
