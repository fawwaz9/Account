import { NavLink } from "react-router-dom";

/** Tabs between Jobs, Applications and Self-employed, which share one place in the sidebar. */
export default function JobsTabs() {
  return (
    <nav className="jobsTabs" aria-label="Jobs sections">
      <NavLink to="/jobs" end className={({ isActive }) => (isActive ? "jobsTab jobsTabActive" : "jobsTab")}>
        Jobs
      </NavLink>
      <NavLink to="/jobs/applications" className={({ isActive }) => (isActive ? "jobsTab jobsTabActive" : "jobsTab")}>
        Applications
      </NavLink>
      <NavLink to="/jobs/self-employed" className={({ isActive }) => (isActive ? "jobsTab jobsTabActive" : "jobsTab")}>
        Self-employed
      </NavLink>
    </nav>
  );
}
