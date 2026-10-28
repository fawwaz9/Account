import { lazy } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import ErrorBoundary from "../shared/components/ErrorBoundary";
import { AuthProvider } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";
import MainLayout from "./layout/MainLayout";
import LoginPage from "../pages/LoginPage";

/**
 * Home page. Every signed-in page is fetched on first visit, not with the app.
 * Add new pages as another `lazy` import: a plain import folds them into the first download.
 */
const Dashboard = lazy(() => import("../pages/Dashboard"));
/** Grades page: the course list. */
const GradesPage = lazy(() => import("../pages/grades/GradesPage"));
/** One course's grades, weights and projections. */
const CourseDetailPage = lazy(() => import("../pages/grades/CourseDetailPage"));
/** Degree requirements and progress. */
const DegreePage = lazy(() => import("../pages/grades/DegreePage"));
/** Calendar page. */
const CalendarPage = lazy(() => import("../pages/CalendarPage"));
/** Tasks page. */
const TasksPage = lazy(() => import("../pages/TasksPage"));
/** Jobs page: jobs, shifts and pay. */
const JobsPage = lazy(() => import("../pages/JobsPage"));
/** Job applications and their seasons. */
const ApplicationsPage = lazy(() => import("../pages/ApplicationsPage"));
/** Budget page (Finances). */
const BudgetPage = lazy(() => import("../pages/BudgetPage"));
/** One money account's activity. */
const AccountDetailPage = lazy(() => import("../pages/budget/AccountDetailPage"));
/** Settings page. */
const SettingsPage = lazy(() => import("../pages/SettingsPage"));
/** Opens an invite link: partner, shared task, shared event or team. */
const InvitePage = lazy(() => import("../pages/InvitePage"));
/** Fitness page: teams. */
const FitnessPage = lazy(() => import("../pages/FitnessPage"));

/** Root: error boundary, session, router; signed-in pages share one guard and shell. */
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
                wrapping each route separately. The shell also carries the
                Suspense boundary these lazy routes need. */}
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
              <Route path="/grades/degree" element={<DegreePage />} />
              <Route path="/calendar" element={<CalendarPage />} />
              <Route path="/tasks" element={<TasksPage />} />
              <Route path="/jobs" element={<JobsPage />} />
              <Route path="/jobs/applications" element={<ApplicationsPage />} />
              {/* Phase 2 item 11: teams, under Fitness. */}
              <Route path="/fitness" element={<FitnessPage />} />
              <Route path="/budget" element={<BudgetPage />} />
              <Route path="/budget/accounts/:accountId" element={<AccountDetailPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              {/* Phase 2 item 10: an invite link. Behind sign-in, and the
                  sign-in page brings you back here with the link intact. */}
              <Route path="/invite" element={<InvitePage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}
