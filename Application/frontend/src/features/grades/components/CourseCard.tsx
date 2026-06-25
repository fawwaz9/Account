import { Course } from "../types";

interface CourseCardProps {
  course: Course;
}

export default function CourseCard({ course }: CourseCardProps) {
  return (
    <div className="border rounded-lg p-4 shadow-sm">
      <h2 className="text-xl font-bold">{course.code}</h2>
      <p>{course.name}</p>
      <p className="text-gray-500">{course.semester}</p>
    </div>
  );
}