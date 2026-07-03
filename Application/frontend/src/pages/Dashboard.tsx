import { useNavigate } from "react-router-dom";
import "../styles/dashboard.css";

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div className="dashboard">
      <h1 className="title">Welcome, Fawwaz</h1>

      <div className="grid">
        <button type="button" className="widget action-widget" onClick={() => navigate("/grades")}>
          <h2>Grades</h2>
          <p>View your courses, marks, and progress.</p>
          <span className="widget-link">Open Grades</span>
        </button>

        <div className="widget disabled" aria-disabled="true">
          <h2>Calendar</h2>
          <p>Coming soon</p>
        </div>
      </div>
    </div>
  );
}