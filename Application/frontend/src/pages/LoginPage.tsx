import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";
import { loginWithGoogle } from "../services/authClient";

declare global {
  interface Window {
    google: any;
  }
}

export default function LoginPage() {
  const buttonRef = useRef<HTMLDivElement>(null);
  const { login } = useAuth();
  const navigate = useNavigate();
  const [scriptError, setScriptError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    function renderButton() {
      if (cancelled || !buttonRef.current) return;

      window.google.accounts.id.initialize({
        client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
        callback: async (response: { credential: string }) => {
          try {
            const { access_token } = await loginWithGoogle(response.credential);
            await login(access_token);
            navigate("/");
          } catch (err) {
            console.error("Login failed:", err);
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

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginTop: "20vh", gap: "1rem" }}>
      {scriptError ? (
        <p style={{ color: "red" }}>
          Couldn't load Google Sign-In. Check that the script tag is in index.html and you're online.
        </p>
      ) : (
        <div ref={buttonRef} />
      )}
    </div>
  );
}