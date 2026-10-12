import { NavLink } from "react-router-dom";
import Icon from "../../shared/components/Icon";
import { NAV, NavItem } from "./Sidebar";

/**
 * The phone's order, as the owner sketched it. Picked out of NAV by route
 * rather than written again, so a label or an icon cannot differ between the
 * sidebar and this bar. Settings is not here: the profile icon in the header
 * reaches it.
 */
export const PHONE_NAV_ORDER = ["/", "/grades", "/tasks", "/budget", "/calendar", "/fitness", "/jobs"];

export const PHONE_NAV: NavItem[] = PHONE_NAV_ORDER.map((to) => {
  const item = NAV.find((candidate) => candidate.to === to);
  if (!item) throw new Error(`PHONE_NAV_ORDER names ${to}, which NAV does not have`);
  return item;
});

/**
 * The bottom icon bar on a phone: fixed, and scrolling sideways, with five
 * icons and a sliver of the sixth showing so it is plain there is more. Icons
 * only, so each link is named for a screen reader; the current page is marked
 * with aria-current, which is also what draws its ring.
 */
export default function BottomNav() {
  return (
    <nav className="phoneNav" aria-label="Main">
      <ul className="phoneNavList">
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
