import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";
import { setPassword } from "../services/authClient";
import "../styles/login.css";

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const hasPassword = user?.has_password ?? false;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);

    try {
      await setPassword(newPassword, hasPassword ? currentPassword : undefined);
      await refreshUser();
      setSuccess(hasPassword ? "Password changed." : "Password set. You can now sign in with your email.");
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="container">
      <div className="mb-6">
        <button type="button" className="buttons" onClick={() => navigate("/")}>
          ←
        </button>
      </div>

      <h1 className="title">Settings</h1>

      <div className="settingsGrid">
        <div className="card">
          <h2>Account</h2>
          <div className="settingsRow">
            <span className="settingsLabel">Name</span>
            <span>{user?.name}</span>
          </div>
          <div className="settingsRow">
            <span className="settingsLabel">Email</span>
            <span>{user?.email}</span>
          </div>
          <div className="settingsRow">
            <span className="settingsLabel">Sign-in methods</span>
            <span>
              <span className={user?.has_google ? "settingsBadge" : "settingsBadge settingsBadgeOff"}>
                Google
              </span>{" "}
              <span className={hasPassword ? "settingsBadge" : "settingsBadge settingsBadgeOff"}>
                Password
              </span>
            </span>
          </div>
        </div>

        <div className="card">
          <h2>{hasPassword ? "Change password" : "Add a password"}</h2>
          <p className="muted small-text">
            {hasPassword
              ? "Enter your current password to set a new one."
              : "Set a password to sign in with your email as well as Google."}
          </p>

          <form className="loginForm" onSubmit={handleSubmit}>
            {hasPassword && (
              <div className="loginField">
                <label htmlFor="current-password">Current password</label>
                <input
                  id="current-password"
                  className="loginInput"
                  type="password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
            )}

            <div className="loginField">
              <label htmlFor="new-password">New password</label>
              <input
                id="new-password"
                className="loginInput"
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                autoComplete="new-password"
                placeholder="At least 8 characters"
                minLength={8}
                required
              />
            </div>

            {error && <p className="loginError">{error}</p>}
            {success && <p className="loginSuccess">{success}</p>}

            <button type="submit" className="loginSubmit" disabled={submitting}>
              {submitting ? "Saving..." : hasPassword ? "Change password" : "Set password"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
