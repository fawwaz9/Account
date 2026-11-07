import { Course } from "../types";
import { useNavigate } from "react-router-dom";

/** The courses to show as cards, and what a final-grade-only card opens. */
interface CourseListProps {
  readonly courses: readonly Course[];
  /** Opens Edit Course for a final-grade-only course; without it, its card opens the page as any other. */
  readonly onEditFinalOnly?: (course: Course) => void;
}

/** The course a card shows. */
interface CourseCardProps {
  readonly course: Course;
  readonly onEditFinalOnly?: (course: Course) => void;
}

/** The grade a course card shows: the recorded final, else a nonzero average, else null. */
export function displayGrade(course: Course): number | null {
  if (course.final_grade > 0) return course.final_grade;
  // Null already means "nothing marked"; the > 0 test remains for a course
  // whose marks average out to zero, which mirrors course_result_grade.
  if (course.average !== null && course.average > 0) return course.average;
  return null;
}

/** The course cards, in the order given. */
export default function CourseList({ courses, onEditFinalOnly }: CourseListProps) {
  return (
    <div className="courseList">
      {courses.map((course) => (
        <CourseCard key={course.id} course={course} onEditFinalOnly={onEditFinalOnly} />
      ))}
    </div>
  );
}

/**
 * One course card: code, section and professor, letter, and the grade to the nearest whole. A
 * final-grade-only course has no page worth opening, so its card stays quiet on hover and
 * opens Edit Course instead.
 */
export function CourseCard({ course, onEditFinalOnly }: CourseCardProps) {
  const navigate = useNavigate();
  const grade = displayGrade(course);
  const finalOnly = Boolean(course.final_only && onEditFinalOnly);

  return (
    <div className={course.archived ? "courses courseArchived" : "courses"}>
      <button
        type="button"
        className={finalOnly ? "courseBox courseBoxFinalOnly" : "courseBox"}
        onClick={() => (finalOnly ? onEditFinalOnly?.(course) : navigate(`/grades/courses/${course.id}`))}
      >
        <span className="courseBoxMain">
          <span className="courseCode">
            {course.code}
            {/* Archived courses are only on screen when asked for, so the mark
                says why this one looks muted rather than dead. */}
            {course.archived && <span className="archivedTag">archived</span>}
            {finalOnly && <span className="archivedTag">final only</span>}
          </span>
          {(course.section || course.professor) && (
            <span className="small-text courseProfessor">
              {[course.section && `Section ${course.section}`, course.professor].filter(Boolean).join(" · ")}
            </span>
          )}
        </span>
        {course.letter_grade && (
          <span className="courseLetter">{course.letter_grade}</span>
        )}
      </button>

      <div className="averageCircle">{grade === null ? "–" : Math.round(grade)}</div>
    </div>
  );
}
