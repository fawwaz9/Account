import { Suspense } from "react";
import { Outlet } from "react-router-dom";
import Loading from "../../shared/components/Loading";
import Sidebar from "./Sidebar";
import BottomNav from "./BottomNav";
import Topbar from "./Topbar";
import KeyboardShortcuts from "./KeyboardShortcuts";
import { useVisitCounter } from "../../shared/hooks/useVisitCounter";
import "../../styles/layout.css";

/**
 * Signed-in shell: sidebar, header and phone bar around the routed page.
 * Suspense wraps only the outlet, so the shell stays put while a page's code loads.
 */
export default function MainLayout() {
  useVisitCounter();

  return (
    <div className="appShell">
      <Sidebar />
      <KeyboardShortcuts />
      <div className="appMain">
        <Topbar />
        <main className="appContent">
          <Suspense fallback={<Loading label="Loading…" />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      {/* Hidden by the stylesheet except on a phone, where it replaces the
          sidebar. Both are always rendered so the switch is pure CSS and a
          rotation never waits on a re-render to have navigation. */}
      <BottomNav />
    </div>
  );
}
