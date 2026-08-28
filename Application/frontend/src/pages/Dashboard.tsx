import { useNavigate } from "react-router-dom";
import "../styles/dashboard.css";
import { useAuth } from "../app/auth/AuthContext"; // adjust path to match your structure

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();

  return (
    <div className="dashboard">
      <h1 className="title">Welcome, {user?.name}</h1>

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
      </div>
    </div>
  );
}