import { useEffect, useState, useCallback, useMemo } from "react";
import { fetchCourses } from "../api";
import { Course } from "../types";
import { getOrCreateUserId } from "../../../services/userService";

export function useCourses() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCourses = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const userId = await getOrCreateUserId();
      const data = await fetchCourses(userId);
      setCourses(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load courses");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCourses();
  }, [loadCourses]);

  return { courses, loading, error, reload: loadCourses };
}

export function useFilteredCourses(
  courses: Course[],
  searchQuery: string
) {

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
