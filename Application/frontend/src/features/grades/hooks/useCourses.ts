import { useEffect, useState, useCallback } from "react";
import { fetchCourses } from "../api";
import { Course } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { useApiRefresh } from "../../../shared/hooks/useApiRefresh";

/** The student's courses with loading, error and `reload`; reloads after a changed refetch. */
export function useCourses() {
  const { user } = useAuth();
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCourses = useCallback(async () => {
    // Clear loading on the way out, or a null user leaves the page stuck on
    // "Loading courses..." forever.
    if (!userId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await fetchCourses(userId);
      setCourses(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load courses");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  // Catch up when a background refetch finds something new (audit #35).
  useApiRefresh(loadCourses);

  useEffect(() => {
    loadCourses();
  }, [loadCourses]);

  return { courses, loading, error, reload: loadCourses };
}
