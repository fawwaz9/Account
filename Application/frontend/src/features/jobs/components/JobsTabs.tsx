import { NavLink } from "react-router-dom";

/** Tabs between Jobs and Applications, which share one place in the sidebar. */
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
