import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";
import { loginWithEmail, loginWithGoogle, registerWithEmail } from "../services/authClient";
import "../styles/login.css";

/** Google Identity Services, loaded by a script tag in index.html. */
declare global {
  interface Window {
    google: any;
  }
}

/** Which form the sign-in card shows. */
type Mode = "signin" | "register";

/**
 * Where to go once signed in: the page that sent you here, or home.
 * Only a same-site path is accepted, so a crafted link cannot send someone off-site.
 */
export function afterSignIn(from: unknown): string {
  if (typeof from !== "string" || !from.startsWith("/") || from.startsWith("//") || from.startsWith("/\\")) {
    return "/";
  }
  return from === "/login" ? "/" : from;
}

/**
 * Sign-in page: Google, or email and password, with a tab to create an account.
 * Waits about ten seconds for the Google script before saying it did not load.
 */
export default function LoginPage() {
  const buttonRef = useRef<HTMLDivElement>(null);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const destination = afterSignIn((location.state as { from?: unknown } | null)?.from);

  const [scriptError, setScriptError] = useState(false);
  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    function renderButton() {
      if (cancelled || !buttonRef.current) return;

      window.google.accounts.id.initialize({
        client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
        callback: async (response: { credential: string }) => {
          setError(null);
          try {
            const { access_token } = await loginWithGoogle(response.credential);
            await login(access_token);
            navigate(destination);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Google sign-in failed");
          }
        },
      });

      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline",
        size: "large",
      });
    }

    if (window.google?.accounts?.id) {
      renderButton();
      return;
    }

    // Script tag is in index.html but may not have loaded yet — poll briefly.
    let attempts = 0;
    const interval = setInterval(() => {
      attempts += 1;
      if (window.google?.accounts?.id) {
        clearInterval(interval);
        renderButton();
      } else if (attempts > 40) {
        // ~10s at 250ms — script never loaded
        clearInterval(interval);
        setScriptError(true);
      }
    }, 250);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [login, navigate]);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setPassword("");
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const { access_token } =
        mode === "signin"
          ? await loginWithEmail(email, password)
          : await registerWithEmail(name, email, password);

      await login(access_token);
      navigate(destination);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  const registering = mode === "register";

  return (
    <div className="loginPage">
      <div className="loginCard">
        <h1 className="loginTitle">Account</h1>
        <p className="loginSubtitle">
          {registering ? "Create your account" : "Sign in to continue"}
        </p>

        <div className="loginTabs">
          <button
            type="button"
            className={mode === "signin" ? "loginTab loginTabActive" : "loginTab"}
            onClick={() => switchMode("signin")}
          >
            Sign in
          </button>
          <button
            type="button"
            className={registering ? "loginTab loginTabActive" : "loginTab"}
            onClick={() => switchMode("register")}
          >
            Create account
          </button>
        </div>

        <form className="loginForm" onSubmit={handleSubmit}>
          {registering && (
            <div className="loginField">
              <label htmlFor="login-name">Name</label>
              <input
                id="login-name"
                className="loginInput"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoComplete="name"
                placeholder="Your name"
                required
              />
            </div>
          )}

          <div className="loginField">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              className="loginInput"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              placeholder="you@example.com"
              required
            />
          </div>

          <div className="loginField">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              className="loginInput"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={registering ? "new-password" : "current-password"}
              placeholder={registering ? "At least 8 characters" : "Your password"}
              minLength={registering ? 8 : undefined}
              required
            />
            {registering && (
              <span className="loginHint">At least 8 characters.</span>
            )}
          </div>

          {error && <p className="loginError">{error}</p>}

          <button type="submit" className="loginSubmit" disabled={submitting}>
            {(() => {
              if (submitting) return "Please wait...";
              return registering ? "Create account" : "Sign in";
            })()}
          </button>
        </form>

        <div className="loginDivider"><span>or</span></div>

        {scriptError ? (
          <p className="loginError">
            Couldn&apos;t load Google Sign-In. Check that the script tag is in index.html
            and you&apos;re online.
          </p>
        ) : (
          <div className="loginGoogle" ref={buttonRef} />
        )}

        <p className="loginFootnote">
          Signing in with Google on an address that already has a password links
          them into one account.
        </p>
      </div>
    </div>
  );
}
