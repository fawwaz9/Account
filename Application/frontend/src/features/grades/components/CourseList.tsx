import { Course } from "../types";
import { useNavigate } from "react-router-dom";

interface CourseListProps {
  readonly courses: readonly Course[];
}

interface CourseCardProps {
  readonly course: Course;
}

export default function CourseList({ courses }: CourseListProps) {
  return (
    <div className="flex flex-col gap-4">
      {courses.map((course) => (
        <CourseCard key={course.id} course={course} />
      ))}
    </div>
  );
}

export function CourseCard({ course }: CourseCardProps) {
  const navigate = useNavigate();

  function gotoDetail() {
    navigate(`/grades/courses/${course.id}`);
  }

  return (
    <div className="courses">
      <button type="button" className="courseBox" onClick={gotoDetail}>
        <h3>{course.code}</h3>
        <p className="small-text">{course.professor}</p>
        <div className="right">
          {/* Implement letter grade later */}
        </div>
      </button>

      <div className="averageCircle">
        {Math.round(
          course.final_grade <= 0 ? course.average : course.final_grade
        )}
      </div>
    </div>
  );
}