import { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from "react";
import { getCurrentUser, CurrentUser } from "../../services/currentUserClient";

interface AuthContextType {
  token: string | null;
  user: CurrentUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { readonly children: ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => sessionStorage.getItem("access_token")
  );
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (token) {
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
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ token, user, isAuthenticated: !!token && !!user, isLoading, login, logout }),
    [token, user, isLoading, login, logout]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}