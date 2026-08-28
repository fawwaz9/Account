import { useEffect, useState, useCallback, useMemo } from "react";
import { fetchCourses } from "../api";
import { Course } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

export function useCourses() {
  const { user } = useAuth();
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCourses = useCallback(async () => {
    // Clear loading on the way out, or a null user leaves the page stuck on
    // "Loading courses..." forever.
    if (!user) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await fetchCourses(user.id);
      setCourses(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load courses");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    loadCourses();
  }, [loadCourses]);

  return { courses, loading, error, reload: loadCourses };
}

export function useFilteredCourses(courses: Course[], searchQuery: string) {
  return useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return courses;
    }

    return courses.filter(
      (course) =>
        course.code.toLowerCase().includes(query) ||
        course.name.toLowerCase().includes(query)
    );
  }, [courses, searchQuery]);
}