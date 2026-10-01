import { useEffect, useState } from "react";
import { useAuth } from "../app/auth/AuthContext";
import { setPassword } from "../services/authClient";
import { updateAcademicStatus, updatePreferences } from "../services/currentUserClient";
import "../styles/login.css";

/**
 * "08:00:00" from the API, "08:00" for an <input type="time">.
 *
 * The server stores a time and serialises seconds; the input binds by exact
 * string, so an unsliced value can render as blank in some browsers.
 */
function clockValue(value: unknown, fallback: string): string {
  return typeof value === "string" ? value.slice(0, 5) : fallback;
}

export default function SettingsPage() {
  const { user, login, refreshUser } = useAuth();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const hasPassword = user?.has_password ?? false;

  const [schoolYear, setSchoolYear] = useState(String(user?.current_school_year ?? ""));
  const [semester, setSemester] = useState(user?.current_semester ?? "Fall");
  const [firstYear, setFirstYear] = useState(
    user?.first_year_calendar_year === null || user?.first_year_calendar_year === undefined
      ? ""
      : String(user.first_year_calendar_year)
  );
  const [creditTarget, setCreditTarget] = useState(String(user?.preferences?.credit_target ?? 120));
  const [gpaEnabled, setGpaEnabled] = useState(user?.preferences?.gpa_scale_enabled ?? true);
  const [defaultTarget, setDefaultTarget] = useState(String(user?.preferences?.default_target_grade ?? 85));
  const [studyStart, setStudyStart] = useState(clockValue(user?.preferences?.study_day_start, "08:00"));
  const [studyEnd, setStudyEnd] = useState(clockValue(user?.preferences?.study_day_end, "22:00"));
  const [minBlock, setMinBlock] = useState(String(user?.preferences?.min_free_block_minutes ?? 30));
  const [academicError, setAcademicError] = useState<string | null>(null);
  const [academicSaved, setAcademicSaved] = useState(false);
  const [savingAcademic, setSavingAcademic] = useState(false);

  // user is null on the first render and arrives once /me resolves, so the
  // initial useState values would otherwise stay blank forever.
  useEffect(() => {
    if (!user) return;
    setSchoolYear(user.current_school_year === null ? "" : String(user.current_school_year));
    setSemester(user.current_semester ?? "Fall");
    setFirstYear(
      user.first_year_calendar_year === null || user.first_year_calendar_year === undefined
        ? ""
        : String(user.first_year_calendar_year)
    );
    setCreditTarget(String(user.preferences?.credit_target ?? 120));
    setGpaEnabled(user.preferences?.gpa_scale_enabled ?? true);
    setDefaultTarget(String(user.preferences?.default_target_grade ?? 85));
    setStudyStart(clockValue(user.preferences?.study_day_start, "08:00"));
    setStudyEnd(clockValue(user.preferences?.study_day_end, "22:00"));
    setMinBlock(String(user.preferences?.min_free_block_minutes ?? 30));
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
        // Number("") is 0, which is a year the validator refuses and a lie
        // besides -- blank means "not set", and terms then have no dates.
        first_year_calendar_year: firstYear === "" ? null : Number(firstYear),
      });
      await updatePreferences(user.id, {
        credit_target: Number(creditTarget),
        gpa_scale_enabled: gpaEnabled,
        default_target_grade: Number(defaultTarget),
        study_day_start: studyStart,
        study_day_end: studyEnd,
        min_free_block_minutes: Number(minBlock),
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
      // The old token is dead the moment this returns -- changing a password
      // invalidates every session the account had. Adopt the replacement before
      // anything else calls the API, or refreshUser() below 401s and bounces to
      // the login page with the password already changed and nothing said.
      const { access_token } = await setPassword(
        newPassword,
        hasPassword ? currentPassword : undefined
      );
      await login(access_token);
      setSuccess(
        hasPassword
          ? "Password changed. Any other signed-in device has been signed out."
          : "Password set. You can now sign in with your email."
      );
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
      <h1 className="title">Settings</h1>

      <div className="settingsGrid">
        {/* Account and Password side by side: one subject, and both are short
            enough that stacking them wasted the width. Everything below is a
            form you work through, which is why the split stops here. */}
        <div className="settingsTop">
          <div className="settingsCard">
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
          <div className="settingsCard">
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

        <div className="settingsPanels">
          <div className="settingsCard">
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
                <label htmlFor="first-year">The year your first year began</label>
                <input
                  id="first-year"
                  className="loginInput"
                  type="number"
                  min={1990}
                  max={2100}
                  value={firstYear}
                  onChange={(event) => setFirstYear(event.target.value)}
                  placeholder="e.g. 2023"
                />
                <span className="muted small-text">
                  A school year is 1, 2, 3 — not a calendar year — so this is what
                  gives each term real dates. Leave it blank and nothing that
                  measures a term can say when it ran.
                </span>
                {/* Worked out from courses that already carry dates, which is
                    evidence rather than a label. Offered rather than applied:
                    getting this wrong shifts every term in the app by a year,
                    and it is the student who knows. */}
                {user?.suggested_first_year != null &&
                  String(user.suggested_first_year) !== firstYear && (
                    <button
                      type="button"
                      className="courseLinkAdd"
                      onClick={() => setFirstYear(String(user.suggested_first_year))}
                    >
                      Your dated courses suggest {user.suggested_first_year} — use it
                    </button>
                  )}
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
                  step="any"
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

              {/* What counts as usable study time. 03:00 is technically free and
                  is not it, so the gaps between classes are only offered inside
                  these hours. */}
              <div className="loginField">
                <label htmlFor="study-start">Study hours</label>
                <div className="studyHoursRow">
                  <input
                    id="study-start"
                    className="loginInput"
                    type="time"
                    value={studyStart}
                    onChange={(event) => setStudyStart(event.target.value)}
                    required
                  />
                  <span className="studyHoursTo">to</span>
                  <input
                    id="study-end"
                    className="loginInput"
                    type="time"
                    value={studyEnd}
                    onChange={(event) => setStudyEnd(event.target.value)}
                    aria-label="Study hours end"
                    required
                  />
                </div>
                <span className="loginHint">
                  The hours free blocks are offered in.
                </span>
              </div>

              <div className="loginField">
                <label htmlFor="min-block">Shortest useful gap</label>
                <input
                  id="min-block"
                  className="loginInput"
                  type="number"
                  min={5}
                  max={240}
                  value={minBlock}
                  onChange={(event) => setMinBlock(event.target.value)}
                  required
                />
                <span className="loginHint">
                  Minutes. Below this a gap is walking time, not study time.
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
        </div>
      </div>
    </div>
  );
}
