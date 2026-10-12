import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import Omnibox from "../../features/omnibox/Omnibox";
import Icon from "../../shared/components/Icon";
import profileIcon from "../../assets/icons/profile_m.png";
import { PHONE_QUERY, useMediaQuery } from "../../shared/hooks/useMediaQuery";

export default function Topbar() {
  const { user, logout } = useAuth();
  const phone = useMediaQuery(PHONE_QUERY);
  const onHome = useLocation().pathname === "/";

  if (phone) {
    // The owner's phone header: the name of the app, and the profile icon,
    // which is the way to Settings -- and so to signing out, which lives there
    // on a phone. The omnibox is on the home screen only: on a small screen
    // every other page needs the room more than it needs a second way in.
    return (
      <header className="topbar phoneTopbar">
        <div className="phoneTopbarRow">
          <span className="phoneBrand">Account</span>
          <Link to="/settings" className="phoneProfile" aria-label="Profile and settings">
            <Icon src={profileIcon} className="phoneProfileIcon" />
          </Link>
        </div>
        {onHome && <Omnibox />}
      </header>
    );
  }

  return (
    <header className="topbar">
      {/* In the shell rather than on a page, because the point of one input for
          everything is not having to navigate to it first. */}
      <Omnibox />

      <div className="topbarRight">
        <span className="topbarUser">{user?.name}</span>
        <button type="button" className="topbarLogout" onClick={logout}>
          Sign out
        </button>
      </div>
    </header>
  );
}
