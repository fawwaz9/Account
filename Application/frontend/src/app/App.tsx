import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";
import LoginPage from "../pages/LoginPage";
import Dashboard from "../pages/Dashboard";
import GradesPage from "../pages/grades/GradesPage";
import CourseDetailPage from "../pages/grades/CourseDetailPage";
import CalendarPage from "../pages/CalendarPage";
import TasksPage from "../pages/TasksPage";
import BudgetPage from "../pages/BudgetPage";
import SettingsPage from "../pages/SettingsPage";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/grades" element={<ProtectedRoute><GradesPage /></ProtectedRoute>} />
          <Route path="/grades/courses/:courseId" element={<ProtectedRoute><CourseDetailPage /></ProtectedRoute>} />
          <Route path="/grades/courses/:courseId/edit" element={<ProtectedRoute><CourseDetailPage /></ProtectedRoute>} />
          <Route path="/grades/courses/:courseId/add" element={<ProtectedRoute><CourseDetailPage /></ProtectedRoute>} />
          <Route path="/calendar" element={<ProtectedRoute><CalendarPage /></ProtectedRoute>} />
          <Route path="/tasks" element={<ProtectedRoute><TasksPage /></ProtectedRoute>} />
          <Route path="/budget" element={<ProtectedRoute><BudgetPage /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}