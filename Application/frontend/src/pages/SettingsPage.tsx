import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";
import { setPassword } from "../services/authClient";
import { updateAcademicStatus, updatePreferences } from "../services/currentUserClient";
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

  const [schoolYear, setSchoolYear] = useState(String(user?.current_school_year ?? ""));
  const [semester, setSemester] = useState(user?.current_semester ?? "Fall");
  const [creditTarget, setCreditTarget] = useState(String(user?.preferences?.credit_target ?? 120));
  const [gpaEnabled, setGpaEnabled] = useState(user?.preferences?.gpa_scale_enabled ?? true);
  const [defaultTarget, setDefaultTarget] = useState(String(user?.preferences?.default_target_grade ?? 85));
  const [academicError, setAcademicError] = useState<string | null>(null);
  const [academicSaved, setAcademicSaved] = useState(false);
  const [savingAcademic, setSavingAcademic] = useState(false);

  // user is null on the first render and arrives once /me resolves, so the
  // initial useState values would otherwise stay blank forever.
  useEffect(() => {
    if (!user) return;
    setSchoolYear(user.current_school_year === null ? "" : String(user.current_school_year));
    setSemester(user.current_semester ?? "Fall");
    setCreditTarget(String(user.preferences?.credit_target ?? 120));
    setGpaEnabled(user.preferences?.gpa_scale_enabled ?? true);
    setDefaultTarget(String(user.preferences?.default_target_grade ?? 85));
  }, [user]);

  async function handleAcademicSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setAcademicError(null);
    setAcademicSaved(false);
    setSavingAcademic(true);

    try {
      // Two endpoints: the term lives on the user record, the targets in
      // preferences. Saved together so one button means one saved state.
      await updateAcademicStatus(user.id, {
        school_year: Number(schoolYear),
        semester,
      });
      await updatePreferences(user.id, {
        credit_target: Number(creditTarget),
        gpa_scale_enabled: gpaEnabled,
        default_target_grade: Number(defaultTarget),
      });
      await refreshUser();
      setAcademicSaved(true);
    } catch (err) {
      setAcademicError(err instanceof Error ? err.message : "Could not save your settings");
    } finally {
      setSavingAcademic(false);
    }
  }

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
          <h2>Academic</h2>
          <p className="muted small-text">
            Your current term decides which courses count as past, current, or future.
          </p>

          <form className="loginForm" onSubmit={handleAcademicSubmit}>
            <div className="loginField">
              <label htmlFor="school-year">Current school year</label>
              <input
                id="school-year"
                className="loginInput"
                type="number"
                min={1}
                max={10}
                value={schoolYear}
                onChange={(event) => setSchoolYear(event.target.value)}
                placeholder="e.g. 2"
                required
              />
            </div>

            <div className="loginField">
              <label htmlFor="current-semester">Current semester</label>
              <select
                id="current-semester"
                className="loginInput"
                value={semester}
                onChange={(event) => setSemester(event.target.value)}
              >
                {["Fall", "Winter", "Spring", "Summer"].map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>

            <div className="loginField">
              <label htmlFor="credit-target">Credits required for your degree</label>
              <input
                id="credit-target"
                className="loginInput"
                type="number"
                min={1}
                max={400}
                value={creditTarget}
                onChange={(event) => setCreditTarget(event.target.value)}
                required
              />
            </div>

            <div className="loginField">
              <label htmlFor="default-target">Default target grade</label>
              <input
                id="default-target"
                className="loginInput"
                type="number"
                min={0}
                max={100}
                value={defaultTarget}
                onChange={(event) => setDefaultTarget(event.target.value)}
                required
              />
              <span className="loginHint">
                Used for any course without its own target.
              </span>
            </div>

            <div className="settingsToggle">
              <input
                id="gpa-enabled"
                type="checkbox"
                checked={gpaEnabled}
                onChange={(event) => setGpaEnabled(event.target.checked)}
              />
              <label htmlFor="gpa-enabled">
                Show CGPA
                <span className="small-text muted">
                  {" "}&mdash; UBC doesn&apos;t put a GPA on transcripts, so this is optional.
                </span>
              </label>
            </div>

            {academicError && <p className="loginError">{academicError}</p>}
            {academicSaved && <p className="loginSuccess">Saved.</p>}

            <button type="submit" className="loginSubmit" disabled={savingAcademic}>
              {savingAcademic ? "Saving..." : "Save"}
            </button>
          </form>
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
