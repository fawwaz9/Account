import { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from "react";
import { getCurrentUser, CurrentUser } from "../../services/currentUserClient";
import { setClockZone } from "../../shared/utils/dateUtils";
import { forgetThisDevice } from "../../features/notifications/push";

/** What `useAuth` exposes: the session token, the user, and the sign-in actions. */
interface AuthContextType {
  /** Bearer token, mirrored in sessionStorage. */
  token: string | null;
  user: CurrentUser | null;
  /** True once both the token and its user are present. */
  isAuthenticated: boolean;
  /** True while the user for the current token is loading. */
  isLoading: boolean;
  /** Store a new token; its user is fetched afterwards. */
  login: (token: string) => Promise<void>;
  /** Unsubscribe this device from push, then drop the session. */
  logout: () => void;
  /** Re-read the user after a server-side change; a failure keeps the old one. */
  refreshUser: () => Promise<void>;
}

/** Session context; undefined outside the provider. */
const AuthContext = createContext<AuthContextType | undefined>(undefined);

/** Session provider: the token, its user from `users/me`, and the clock set to their zone. */
export function AuthProvider({ children }: { readonly children: ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => sessionStorage.getItem("access_token")
  );
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (token) {
      // Mark loading again while the profile for a *new* token is fetched.
      // Without this, the moment after login the token is set but user is
      // still null, so isAuthenticated reads false and ProtectedRoute
      // redirects back to /login before the fetch resolves.
      setIsLoading(true);
      sessionStorage.setItem("access_token", token);
      getCurrentUser()
        .then(setUser)
        .catch(() => {
          // token invalid/expired — clear everything
          sessionStorage.removeItem("access_token");
          setToken(null);
          setUser(null);
        })
        .finally(() => setIsLoading(false));
    } else {
      sessionStorage.removeItem("access_token");
      setUser(null);
      setIsLoading(false);
    }
  }, [token]);

  const login = useCallback(async (newToken: string) => {
    setToken(newToken); // triggers the effect above, which fetches user
  }, []);

  const logout = useCallback(() => {
    // Before anything else, and without waiting: a shared computer must stop
    // receiving this person's reminders the moment they sign out.
    forgetThisDevice();
    setToken(null);
    setUser(null);
  }, []);

  // Re-read the profile after something changes it server-side, e.g. adding a
  // password, so has_password stops being stale.
  const refreshUser = useCallback(async () => {
    try {
      setUser(await getCurrentUser());
    } catch {
      // leave the existing user in place; the 401 path already handles expiry
    }
  }, []);

  // During render, not in an effect: children render after this body in the
  // same pass, so the first today() any page asks for is already on the
  // student's clock. An effect would run after they had rendered, and the page
  // would open on the browser's day and flip. Idempotent for a given user.
  setClockZone(user?.preferences?.timezone);

  const value = useMemo(
    () => ({ token, user, isAuthenticated: !!token && !!user, isLoading, login, logout, refreshUser }),
    [token, user, isLoading, login, logout, refreshUser]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/** Read the session; throws outside the provider. */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}