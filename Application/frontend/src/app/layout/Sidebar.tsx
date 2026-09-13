import { NavLink } from "react-router-dom";

interface NavItem {
  readonly to: string;
  readonly label: string;
  /** end so "/" only matches the dashboard, not every route beneath it */
  readonly end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/grades", label: "Grades" },
  { to: "/calendar", label: "Calendar" },
  { to: "/tasks", label: "Tasks" },
  { to: "/jobs", label: "Jobs" },
  { to: "/budget", label: "Budget" },
  { to: "/settings", label: "Settings" },
];

export default function Sidebar() {
  return (
    <nav className="sidebar" aria-label="Main">
      <span className="sidebarBrand">Account</span>

      <ul className="sidebarNav">
        {NAV.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? "sidebarLink sidebarLinkActive" : "sidebarLink"
              }
            >
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
