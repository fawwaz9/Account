import { useAuth } from "../auth/AuthContext";
import Omnibox from "../../features/omnibox/Omnibox";

export default function Topbar() {
  const { user, logout } = useAuth();

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
