import { Navigate, useLocation } from "react-router-dom";
import Loading from "../../shared/components/Loading";
import { useAuth } from "./AuthContext";

export default function ProtectedRoute({ children }: { readonly children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    // Rendering null here gave a blank white page on every cold load, for as
    // long as the session check took -- indistinguishable from the app being
    // broken.
    return <Loading label="Signing you in…" />;
  }

  if (!isAuthenticated) {
    // Where you were headed, so signing in takes you back there -- an invite
    // link opened while signed out must survive the trip (Phase 2 item 10).
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/login" replace state={{ from }} />;
  }

  return <>{children}</>;
}
