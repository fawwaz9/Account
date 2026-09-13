import { Course } from "../types";
import { useNavigate } from "react-router-dom";

interface CourseListProps {
  readonly courses: readonly Course[];
}

interface CourseCardProps {
  readonly course: Course;
}

/**
 * The grade a course should be represented by: the professor's final grade
 * once submitted, otherwise the running average. Mirrors course_result_grade
 * on the backend, which is what letter_grade is derived from.
 */
export function displayGrade(course: Course): number | null {
  if (course.final_grade > 0) return course.final_grade;
  // Null already means "nothing marked"; the > 0 test remains for a course
  // whose marks average out to zero, which mirrors course_result_grade.
  if (course.average !== null && course.average > 0) return course.average;
  return null;
}

export default function CourseList({ courses }: CourseListProps) {
  return (
    <div className="courseList">
      {courses.map((course) => (
        <CourseCard key={course.id} course={course} />
      ))}
    </div>
  );
}

export function CourseCard({ course }: CourseCardProps) {
  const navigate = useNavigate();
  const grade = displayGrade(course);

  return (
    <div className={course.archived ? "courses courseArchived" : "courses"}>
      <button
        type="button"
        className="courseBox"
        onClick={() => navigate(`/grades/courses/${course.id}`)}
      >
        <span className="courseBoxMain">
          <span className="courseCode">
            {course.code}
            {/* Archived courses are only on screen when asked for, so the mark
                says why this one looks muted rather than dead. */}
            {course.archived && <span className="archivedTag">archived</span>}
          </span>
          {course.professor && (
            <span className="small-text courseProfessor">{course.professor}</span>
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
