export interface Course {
  id: number;
  name: string;
  code: string;
  semester: string;
}

export interface Assignment {
  id: number;
  courseId: number;
  name: string;
  weight: number;
  grade: number | null;
}