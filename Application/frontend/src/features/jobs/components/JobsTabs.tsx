import { NavLink } from "react-router-dom";

/**
 * Jobs and Applications, side by side under Jobs (Phase 3 item 1). The jobs you
 * have and the ones you're after are different pages, but one place in the
 * sidebar.
 */
export default function JobsTabs() {
  return (
    <nav className="jobsTabs" aria-label="Jobs sections">
      <NavLink to="/jobs" end className={({ isActive }) => (isActive ? "jobsTab jobsTabActive" : "jobsTab")}>
        Jobs
      </NavLink>
      <NavLink to="/jobs/applications" className={({ isActive }) => (isActive ? "jobsTab jobsTabActive" : "jobsTab")}>
        Applications
      </NavLink>
    </nav>
  );
}
