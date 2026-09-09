import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import "../../styles/layout.css";

/**
 * Shell for every signed-in page. Replaces the per-page back arrows that were
 * the only navigation across seven pages.
 */
export default function MainLayout() {
  return (
    <div className="appShell">
      <Sidebar />
      <div className="appMain">
        <Topbar />
        <main className="appContent">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
