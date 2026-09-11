import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { searchCourses } from "../api";
import { Course } from "../types";
import { getErrorMessage } from "./AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";
import { useDebounce } from "../../../shared/hooks/useDebounce";

/**
 * Typeahead over every course, not just the ones on screen.
 *
 * The list beside it shows the current term only, so filtering that list could
 * never reach a past course. This searches server-side across all terms and
 * opens whichever course you pick.
 */
export default function CourseSearch() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Course[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState(-1);

  const debouncedQuery = useDebounce(query, 250);
  const containerRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    const term = debouncedQuery.trim();
    if (!user || term === "") {
      setResults([]);
      setOpen(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    searchCourses(user.id, term)
      .then((data) => {
        if (cancelled) return;
        setResults(data);
        setHighlighted(-1);
        setOpen(true);
      })
      .catch((err) => {
        if (cancelled) return;
        setResults([]);
        setError(getErrorMessage(err));
        setOpen(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, user]);

  // Clicking anywhere else dismisses the dropdown.
  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function openCourse(course: Course) {
    setOpen(false);
    setQuery("");
    navigate(`/grades/courses/${course.id}`);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }

    if (!open || results.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((current) => (current + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((current) => (current <= 0 ? results.length - 1 : current - 1));
    } else if (event.key === "Enter" && highlighted >= 0) {
      event.preventDefault();
      openCourse(results[highlighted]);
    }
  }

  const showDropdown = open && query.trim() !== "";

  return (
    <div className="courseSearch" ref={containerRef}>
      <input
        className="search-courses"
        id="search-courses"
        type="search"
        role="combobox"
        aria-expanded={showDropdown}
        aria-controls={listId}
        aria-autocomplete="list"
        placeholder="Search all courses..."
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        onKeyDown={handleKeyDown}
      />

      {showDropdown && (
        <ul className="searchResults" id={listId}>
          {(() => {
            if (loading) {
              return <li className="searchStatus">Searching...</li>;
            }
            if (error) {
              return <li className="searchStatus">{error}</li>;
            }
            if (results.length === 0) {
              return <li className="searchStatus">No courses match &ldquo;{query}&rdquo;.</li>;
            }
            return results.map((course, index) => (
              <li key={course.id}>
                <button
                  type="button"
                  className={index === highlighted ? "searchResult searchResultActive" : "searchResult"}
                  onClick={() => openCourse(course)}
                  onMouseEnter={() => setHighlighted(index)}
                >
                  <span className="searchResultCode">{course.code}</span>
                  <span className="searchResultName">{course.name}</span>
                </button>
              </li>
            ));
          })()}
        </ul>
      )}
    </div>
  );
}
