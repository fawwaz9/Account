import { Navigate } from "react-router-dom";
import Loading from "../../shared/components/Loading";
import { useAuth } from "./AuthContext";

export default function ProtectedRoute({ children }: { readonly children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    // Rendering null here gave a blank white page on every cold load, for as
    // long as the session check took -- indistinguishable from the app being
    // broken.
    return <Loading label="Signing you in…" />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
