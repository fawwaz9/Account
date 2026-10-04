import { NavLink } from "react-router-dom";

interface NavItem {
  readonly to: string;
  readonly label: string;
  /** end so "/" only matches the dashboard, not every route beneath it */
  readonly end?: boolean;
  /** The letter after G that goes here (KeyboardShortcuts reads this list). */
  readonly key: string;
}

export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", end: true, key: "d" },
  { to: "/grades", label: "Grades", key: "g" },
  { to: "/calendar", label: "Calendar", key: "c" },
  { to: "/tasks", label: "Tasks", key: "t" },
  { to: "/jobs", label: "Jobs", key: "j" },
  { to: "/budget", label: "Budget", key: "b" },
  { to: "/settings", label: "Settings", key: "s" },
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
