import { useAuth } from "../auth/AuthContext";

export default function Topbar() {
  const { user, logout } = useAuth();

  return (
    <header className="topbar">
      <span className="topbarUser">{user?.name}</span>
      <button type="button" className="topbarLogout" onClick={logout}>
        Sign out
      </button>
    </header>
  );
}
