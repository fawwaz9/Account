import { useNavigate } from "react-router-dom";
import "../styles/dashboard.css";
import { useAuth } from "../app/auth/AuthContext";
import { useDashboard } from "../features/grades/hooks/useDashboard";

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const { summary, error: summaryError } = useDashboard();

  const hasCourses = (summary?.total_courses ?? 0) > 0;

  return (
    <div className="dashboard">
      <h1 className="title">Welcome, {user?.name}</h1>

      {summaryError && <p className="muted">{summaryError}</p>}

      {hasCourses && summary && (
        <section className="gradeSummary">
          <div className="summaryStats">
            <div className="statBlock">
              <span className="statValue">{summary.overall_average}</span>
              <span className="statLabel">Average</span>
            </div>
            <div className="statBlock">
              <span className="statValue">{summary.cumulative_average}</span>
              <span className="statLabel">Credit-weighted</span>
            </div>
            <div className="statBlock">
              <span className="statValue">{summary.total_courses}</span>
              <span className="statLabel">Courses</span>
            </div>
          </div>

          {summary.best_course && summary.weakest_course && (
            <div className="summaryCourses">
              <p>
                Strongest <strong>{summary.best_course.course_code}</strong>{" "}
                <span className="muted">{summary.best_course.average}</span>
              </p>
              <p>
                Weakest <strong>{summary.weakest_course.course_code}</strong>{" "}
                <span className="muted">{summary.weakest_course.average}</span>
              </p>
            </div>
          )}
        </section>
      )}

      <div className="grid">
        <button type="button" className="widget action-widget" onClick={() => navigate("/grades")}>
          <h2>Grades</h2>
          <p>View your courses, marks, and progress.</p>
        </button>

        <button type="button" className="widget action-widget" onClick={() => navigate("/calendar")}>
          <h2>Calendar</h2>
          <p>View your schedule and create events.</p>
        </button>

        <button type="button" className="widget action-widget" onClick={() => navigate("/tasks")}>
          <h2>Tasks</h2>
          <p>See your task list powered by the backend.</p>
        </button>

        <button type="button" className="widget action-widget" onClick={() => navigate("/budget")}>
          <h2>Budget</h2>
          <p>Review budgets and manage your spending.</p>
        </button>

        <button type="button" className="widget action-widget" onClick={() => navigate("/settings")}>
          <h2>Settings</h2>
          <p>Manage your account and sign-in methods.</p>
        </button>
      </div>
    </div>
  );
}
