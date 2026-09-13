import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";

export default function ProtectedRoute({ children }: { readonly children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    // Rendering null here gave a blank white page on every cold load, for as
    // long as the session check took -- indistinguishable from the app being
    // broken. `<output>` carries the status role natively, which is what
    // S6819 asks for over a div with role="status".
    return (
      <output className="authBootstrap">
        <span className="authBootstrapSpinner" aria-hidden="true" />
        <span className="small-text muted">Signing you in…</span>
      </output>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
