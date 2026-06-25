import CourseList from "../features/grades/components/CourseList";
import { Course } from "../features/grades/types";

export default function GradesPage() {
  const courses: Course[] = [
    {
      id: 1,
      code: "COSC 111",
      name: "Introduction to Programming",
      semester: "Winter 2026",
    },
    {
      id: 2,
      code: "MATH 225",
      name: "Linear Algebra",
      semester: "Winter 2026",
    },
  ];

  return (
    <div className="p-6">
      <h1 className="text-3xl font-bold mb-6">Grades</h1>

      <CourseList courses={courses} />
    </div>
  );
}