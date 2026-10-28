import { NavLink } from "react-router-dom";
import Icon from "../../shared/components/Icon";
import homeIcon from "../../assets/icons/home_m.png";
import gradesIcon from "../../assets/icons/grades_m.png";
import calendarIcon from "../../assets/icons/calendar_m.png";
import tasksIcon from "../../assets/icons/tasks_m.png";
import jobsIcon from "../../assets/icons/jobs_m.png";
import fitnessIcon from "../../assets/icons/fitness_m.png";
import budgetIcon from "../../assets/icons/budget_m.png";
import settingsIcon from "../../assets/icons/settings_m.png";

/** One main-navigation entry. */
export interface NavItem {
  readonly to: string;
  readonly label: string;
  /** Match the path exactly, so / is only the dashboard. */
  readonly end?: boolean;
  /** Letter pressed after G to jump here. */
  readonly key: string;
  /** Icon image, beside the label here and alone in the phone bar. */
  readonly icon: string;
}

/** Main pages in order; the phone bar and the G shortcuts read it too. */
export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", end: true, key: "d", icon: homeIcon },
  { to: "/grades", label: "Grades", key: "g", icon: gradesIcon },
  { to: "/calendar", label: "Calendar", key: "c", icon: calendarIcon },
  { to: "/tasks", label: "Tasks", key: "t", icon: tasksIcon },
  { to: "/jobs", label: "Jobs", key: "j", icon: jobsIcon },
  { to: "/fitness", label: "Fitness", key: "f", icon: fitnessIcon },
  { to: "/budget", label: "Budget", key: "b", icon: budgetIcon },
  { to: "/settings", label: "Settings", key: "s", icon: settingsIcon },
];

/** Desktop sidebar: the brand and a link per main page. */
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
              <Icon src={item.icon} className="sidebarIcon" />
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
