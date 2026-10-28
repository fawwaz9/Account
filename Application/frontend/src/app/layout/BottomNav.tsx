import { useEffect, useRef } from "react";
import { NavLink, useLocation } from "react-router-dom";
import Icon from "../../shared/components/Icon";
import { NAV, NavItem } from "./Sidebar";

/** Routes in the phone bar's order; Settings is reached from the header instead. */
export const PHONE_NAV_ORDER = ["/", "/grades", "/tasks", "/budget", "/calendar", "/fitness", "/jobs"];

/** The phone bar's items, picked from NAV so labels and icons match the sidebar. */
export const PHONE_NAV: NavItem[] = PHONE_NAV_ORDER.map((to) => {
  const item = NAV.find((candidate) => candidate.to === to);
  if (!item) throw new Error(`PHONE_NAV_ORDER names ${to}, which NAV does not have`);
  return item;
});

/** Phone bottom bar: icon-only links scrolling sideways, the current one kept in view. */
export default function BottomNav() {
  const listRef = useRef<HTMLUListElement>(null);
  const { pathname } = useLocation();

  // Bring the current page's icon into view: on Jobs, the sixth and seventh
  // icons sit past the edge, and a highlight nobody can see marks nothing.
  useEffect(() => {
    const current = listRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
    current?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [pathname]);

  return (
    <nav className="phoneNav" aria-label="Main">
      <ul className="phoneNavList" ref={listRef}>
        {PHONE_NAV.map((item) => (
          <li key={item.to} className="phoneNavItem">
            <NavLink to={item.to} end={item.end} className="phoneNavLink" aria-label={item.label}>
              <Icon src={item.icon} className="phoneNavIcon" />
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
