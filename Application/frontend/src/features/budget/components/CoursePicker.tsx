import { useEffect, useRef, useState } from "react";
import { Course } from "../../grades/types";
import { resolveCourse } from "../api";

/** Props for the course picker. */
interface CoursePickerProps {
  readonly userId: string;
  readonly courses: readonly Course[];
  readonly value: string;
  readonly onChange: (courseId: string) => void;
  /** Watched for a course code, to pre-fill the choice. */
  readonly description: string;
  /** Prefix for the select's id, unique per form. */
  readonly idPrefix: string;
}

/**
 * Which course an expense was for, pre-filled from a code in the description.
 * The server resolves the code; a suggestion only ever fills an empty choice.
 */
export default function CoursePicker({
  userId,
  courses,
  value,
  onChange,
  description,
  idPrefix,
}: CoursePickerProps) {
  const [suggested, setSuggested] = useState<string | null>(null);
  // Typing outruns the round trip, so an older answer could otherwise land last
  // and suggest a course for text that has since been edited away.
  const latestRequest = useRef(0);
  // Whether the current value got there by suggestion, so the note can say so
  // without claiming credit for a course the user picked themselves.
  const filledBySuggestion = useRef(false);

  useEffect(() => {
    const text = description.trim();
    if (!text) {
      setSuggested(null);
      return;
    }

    const ticket = ++latestRequest.current;
    let cancelled = false;

    const timer = setTimeout(() => {
      resolveCourse(userId, text)
        .then((found) => {
          if (cancelled || ticket !== latestRequest.current) return;
          setSuggested(found.course_id);
          // Only ever fills a blank. A course already chosen stands.
          if (found.course_id && !value) {
            filledBySuggestion.current = true;
            onChange(found.course_id);
          }
        })
        .catch(() => {
          if (!cancelled && ticket === latestRequest.current) setSuggested(null);
        });
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // `value` is read but deliberately not a dependency: re-running on every
    // keystroke of the course choice would fight the user for the field.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, description]);

  if (courses.length === 0) return null;

  const showNote = Boolean(value) && value === suggested && filledBySuggestion.current;

  return (
    <div className="loginField">
      <label htmlFor={`${idPrefix}-course`}>Course</label>
      <select
        id={`${idPrefix}-course`}
        className="loginInput"
        value={value}
        onChange={(event) => {
          filledBySuggestion.current = false;
          onChange(event.target.value);
        }}
      >
        <option value="">Not for a course</option>
        {courses.map((course) => (
          <option key={course.id} value={course.id}>
            {course.code} — {course.name}
          </option>
        ))}
      </select>
      {showNote && <p className="courseHint">★ read from the description</p>}
    </div>
  );
}
