import { lazy } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import ErrorBoundary from "../shared/components/ErrorBoundary";
import { AuthProvider } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";
import MainLayout from "./layout/MainLayout";
import LoginPage from "../pages/LoginPage";

/**
 * Every signed-in page is fetched when it is first opened, not with the app.
 *
 * Before this the build was a single 487 KB file, so the login screen
 * downloaded Grades, Calendar, Tasks, Jobs, Budget and Settings before it could
 * draw a password field -- and paid it again on every cache miss. Almost none
 * of that code can run until somebody signs in.
 *
 * `LoginPage` is deliberately **not** lazy. It is the only thing an
 * unauthenticated visitor needs, so loading it on demand would add a second
 * round trip to the one screen that has nothing else to wait for.
 *
 * The shell is eager too -- `MainLayout`, `ProtectedRoute`, `AuthProvider`,
 * `ErrorBoundary` -- because every signed-in page needs all four, so deferring
 * them would buy nothing and cost a request.
 *
 * Two consequences worth knowing before adding a route:
 *
 * - **A new page belongs here as another `lazy()`.** A static import silently
 *   folds it back into the first download, and nothing fails to tell you.
 * - **A chunk can now fail to load** -- notably for a tab left open across a
 *   deploy, which is asking for file names this release no longer serves.
 *   React re-throws that during render, `ErrorBoundary` catches it, and
 *   `shared/utils/chunkErrors.ts` is what tells it apart from a real fault.
 */
const Dashboard = lazy(() => import("../pages/Dashboard"));
const GradesPage = lazy(() => import("../pages/grades/GradesPage"));
const CourseDetailPage = lazy(() => import("../pages/grades/CourseDetailPage"));
const DegreePage = lazy(() => import("../pages/grades/DegreePage"));
const CalendarPage = lazy(() => import("../pages/CalendarPage"));
const TasksPage = lazy(() => import("../pages/TasksPage"));
const JobsPage = lazy(() => import("../pages/JobsPage"));
const BudgetPage = lazy(() => import("../pages/BudgetPage"));
const AccountDetailPage = lazy(() => import("../pages/budget/AccountDetailPage"));
const SettingsPage = lazy(() => import("../pages/SettingsPage"));
const InvitePage = lazy(() => import("../pages/InvitePage"));
const TeamsPage = lazy(() => import("../pages/TeamsPage"));

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
              {/* Phase 2 item 11. */}
              <Route path="/teams" element={<TeamsPage />} />
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
