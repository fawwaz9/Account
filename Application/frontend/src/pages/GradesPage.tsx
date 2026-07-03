import CourseList from "../features/grades/components/CourseList";
import { testCourses } from "../testData/courses";

export default function GradesPage() {
  return (
    <div className="container">
      <h1>Grades</h1>

      <div className="card">
        <CourseList courses={testCourses} />
      </div>
    </div>
  );
}