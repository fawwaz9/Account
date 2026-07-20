import { useState } from "react";
import { useNavigate } from "react-router-dom";
import CourseList from "../../features/grades/components/CourseList";
import AddCourseModal from "../../features/grades/components/AddCourseModal";
import {useCourses, useFilteredCourses} from "../../features/grades/hooks/useCourses";
import CourseSearch from "../../features/grades/components/CourseSearch";

export default function GradesPage() {
  const { courses, loading, error, reload } = useCourses();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const navigate = useNavigate();
  const filteredCourses = useFilteredCourses(courses, searchQuery);

  return (
    <>
      <div className="container">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div className="title">
            <h1>Grades</h1>
          </div>
          <div className="flex gap-2">
            <div className="space-between">
              <button
                type="button"
                onClick={() => navigate('/')}
                className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
              >
                ←
              </button>

              <CourseSearch
                value={searchQuery}
                onChange={setSearchQuery}
              />
            </div>

            <h2> Current Courses </h2>

            <div className="card">
              {loading && <p>Loading courses from backend...</p>}
              {error && <p className="muted">{error}</p>}
              {!loading && !error && courses.length === 0 && (
                <p className="muted">No courses found yet. Use Add Course to create one.</p>
              )}
              {!loading && !error && courses.length > 0 && <CourseList courses={filteredCourses} />}
            </div>

            <button
              type="button"
              onClick={() => setIsModalOpen(true)}
              className="rounded-lg border border-slate-700 bg-gold px-4 py-2 font-semibold text-slate-950"
            >
              Add Course
            </button>
          </div>
        </div>

        
      </div>

      <AddCourseModal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCourseAdded={() => reload()}
      />
    </>
  );
}
