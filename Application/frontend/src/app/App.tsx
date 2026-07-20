import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "../pages/Dashboard";
import GradesPage from "../pages/grades/GradesPage";
import CourseDetailPage from "../pages/grades/CourseDetailPage";
import CalendarPage from "../pages/CalendarPage";
import TasksPage from "../pages/TasksPage";
import BudgetPage from "../pages/BudgetPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/grades" element={<GradesPage />} />
        <Route path="/grades/courses/:courseId" element={<CourseDetailPage />} />
        <Route path="/grades/courses/:courseId/edit" element={<CourseDetailPage />} />
        <Route path="/grades/courses/:courseId/add" element={<CourseDetailPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/budget" element={<BudgetPage />} />
      </Routes>
    </BrowserRouter>
  );
}
