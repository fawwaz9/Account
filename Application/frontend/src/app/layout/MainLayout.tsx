import { Suspense } from "react";
import { Outlet } from "react-router-dom";
import Loading from "../../shared/components/Loading";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import "../../styles/layout.css";

/**
 * Shell for every signed-in page. Replaces the per-page back arrows that were
 * the only navigation across seven pages.
 *
 * The boundary sits here, around `<Outlet />`, rather than around `<Routes>` in
 * `App`. Every page is loaded on demand now, and wrapping the router would blank
 * the sidebar and the topbar while a route's code arrived -- so a navigation
 * would clear the very controls you had just used, which reads as the app
 * restarting rather than as a page turning. This way the shell stays put and
 * only the content area waits.
 *
 * One boundary covers all nine signed-in routes, since they all render through
 * this outlet.
 */
export default function MainLayout() {
  return (
    <div className="appShell">
      <Sidebar />
      <div className="appMain">
        <Topbar />
        <main className="appContent">
          <Suspense fallback={<Loading label="Loading…" />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
