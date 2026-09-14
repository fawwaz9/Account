import { BrowserRouter, Routes, Route } from "react-router-dom";
import ErrorBoundary from "../shared/components/ErrorBoundary";
import { AuthProvider } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";
import MainLayout from "./layout/MainLayout";
import LoginPage from "../pages/LoginPage";
import Dashboard from "../pages/Dashboard";
import GradesPage from "../pages/grades/GradesPage";
import CourseDetailPage from "../pages/grades/CourseDetailPage";
import CalendarPage from "../pages/CalendarPage";
import TasksPage from "../pages/TasksPage";
import JobsPage from "../pages/JobsPage";
import BudgetPage from "../pages/BudgetPage";
import AccountDetailPage from "../pages/budget/AccountDetailPage";
import SettingsPage from "../pages/SettingsPage";

export default function App() {
  return (
    /* Outside the provider as well as the router, not just around the routes.
       A boundary placed inside AuthProvider cannot catch AuthProvider throwing,
       and "the app failed while working out whether you are signed in" is
       exactly the failure a person would otherwise see as a white screen. */
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            {/* One guard and one shell for every signed-in page, rather than
                wrapping each route separately. */}
            <Route
              element={
                <ProtectedRoute>
                  <MainLayout />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<Dashboard />} />
              <Route path="/grades" element={<GradesPage />} />
              <Route path="/grades/courses/:courseId" element={<CourseDetailPage />} />
              <Route path="/calendar" element={<CalendarPage />} />
              <Route path="/tasks" element={<TasksPage />} />
              <Route path="/jobs" element={<JobsPage />} />
              <Route path="/budget" element={<BudgetPage />} />
              <Route path="/budget/accounts/:accountId" element={<AccountDetailPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}
