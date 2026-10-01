import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../app/auth/AuthContext";
import { setPassword } from "../services/authClient";
import { updateAcademicStatus, updatePreferences } from "../services/currentUserClient";
import { fetchAccounts, fetchCategories } from "../features/budget/api";
import { Account, SpendCategory } from "../features/budget/types";
import IncomeSplitModal from "../features/budget/components/IncomeSplitModal";
import CategoriesModal from "../features/budget/components/CategoriesModal";
import "../styles/login.css";
// The two budget modals reached from the Financial tab style their rows from
// budget.css, and nothing else here imports it. In a production build this would
// not matter -- `cssCodeSplit: false` concatenates every stylesheet into one --
// but the dev server injects CSS per imported module, so without this those rows
// render unstyled on /settings until /budget has been visited.
import "../styles/budget.css";

/**
 * "08:00:00" from the API, "08:00" for an <input type="time">.
 *
 * The server stores a time and serialises seconds; the input binds by exact
 * string, so an unsliced value can render as blank in some browsers.
 */
function clockValue(value: unknown, fallback: string): string {
  return typeof value === "string" ? value.slice(0, 5) : fallback;
}

/**
 * The three groups, in the order they are read.
 *
 * Academic leads because it is the one most often wrong at the start of a term,
 * and it is the default for the same reason.
 */
const TABS = [
  { id: "academic", label: "Academic" },
  { id: "calendar", label: "Calendar" },
  { id: "financial", label: "Financial" },
] as const;

type TabId = (typeof TABS)[number]["id"];

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

  // The calendar group saves on its own, so it needs its own trio rather than
  // sharing the academic one -- a "Saved." under one form while the other failed
  // is worse than no message.
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [calendarSaved, setCalendarSaved] = useState(false);
  const [savingCalendar, setSavingCalendar] = useState(false);

  /**
   * Which group is on screen.
   *
   * Only this one value. Every field's state is already held here at page level,
   * so a hidden panel unmounts nothing that holds a value and unsaved typing
   * survives a tab switch for free -- which is the agreed behaviour, not a
   * happy accident, so there is a test for it.
   */
  const [active, setActive] = useState<TabId>("academic");
  const tablistRef = useRef<HTMLDivElement>(null);

  // What the Financial tab's two modals need. Two GETs rather than `useBudget`,
  // which returns these alongside six other reads and a `runRecurring` write --
  // a cost the budget page is right to pay and a settings page is not.
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<SpendCategory[]>([]);
  const [splitOpen, setSplitOpen] = useState(false);
  const [categoriesOpen, setCategoriesOpen] = useState(false);

  const loadMoneyBits = useCallback(async () => {
    if (!user) return;
    const [nextAccounts, nextCategories] = await Promise.all([
      fetchAccounts(user.id).catch(() => [] as Account[]),
      fetchCategories(user.id).catch(() => [] as SpendCategory[]),
    ]);
    setAccounts(nextAccounts);
    setCategories(nextCategories);
  }, [user]);

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

  // Fetched once, not per tab open: two GETs on a page you visit to change one
  // thing, and the Financial tab is one click away whichever tab you land on.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!user) return;
      const [nextAccounts, nextCategories] = await Promise.all([
        fetchAccounts(user.id).catch(() => [] as Account[]),
        fetchCategories(user.id).catch(() => [] as SpendCategory[]),
      ]);
      if (cancelled) return;
      setAccounts(nextAccounts);
      setCategories(nextCategories);
    })();
    return () => { cancelled = true; };
  }, [user]);

  /**
   * Arrow keys move between tabs, which is what makes one tab stop honest.
   *
   * A tablist takes a single Tab stop -- the inactive tabs are `tabIndex={-1}` --
   * so without this a keyboard user could reach the strip and then never change
   * what it shows. Selection follows focus, so there is nothing to press.
   */
  function handleTabKeys(event: React.KeyboardEvent) {
    const order: readonly TabId[] = TABS.map((tab) => tab.id);
    const at = order.indexOf(active);

    let next: number | null = null;
    if (event.key === "ArrowRight") next = (at + 1) % order.length;
    else if (event.key === "ArrowLeft") next = (at - 1 + order.length) % order.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = order.length - 1;
    if (next === null) return;

    event.preventDefault();
    setActive(order[next]);
    // Focus has to follow, or the arrow keys move a selection the user's focus
    // has been left behind by and the next arrow press starts from the old place.
    const buttons = tablistRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[next]?.focus();
  }

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
      // Only this tab's three keys. Sending the study window from here too would
      // mean two forms claiming the same preferences, and whichever saved last
      // would win with whatever was on screen when it did.
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

  /**
   * The calendar group: the study window, and nothing else.
   *
   * **This is only safe because the API takes a real partial patch.** Until
   * `UserUpdate` took `UserPreferencesPatch`, a request naming three preferences
   * was parsed into all fourteen and the merge wrote defaults over the rest -- so
   * saving here would have reset the credit target and the default grade, and
   * saving those would have reset the study window. Per-tab saves are what that
   * fix bought.
   */
  async function handleCalendarSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setCalendarError(null);
    setCalendarSaved(false);
    setSavingCalendar(true);

    try {
      await updatePreferences(user.id, {
        study_day_start: studyStart,
        study_day_end: studyEnd,
        min_free_block_minutes: Number(minBlock),
      });
      await refreshUser();
      setCalendarSaved(true);
    } catch (err) {
      setCalendarError(err instanceof Error ? err.message : "Could not save your settings");
    } finally {
      setSavingCalendar(false);
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
          {/* A real tablist, not a row of toggle buttons: one Tab stop, arrow
              keys inside it, `aria-selected` on the chosen one and a panel that
              names the tab controlling it. The calendar page's view switch next
              door is an `aria-pressed` group, which is a different control for a
              different job -- two buttons that each do something, rather than
              three labels for one region. */}
          <div
            className="settingsTabs"
            role="tablist"
            aria-label="Settings sections"
            ref={tablistRef}
          >
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                id={`settings-tab-${tab.id}`}
                aria-selected={active === tab.id}
                aria-controls={`settings-panel-${tab.id}`}
                // One stop for the whole strip. Arrow keys do the rest.
                tabIndex={active === tab.id ? 0 : -1}
                className={active === tab.id ? "settingsTab settingsTabActive" : "settingsTab"}
                onClick={() => setActive(tab.id)}
                // On the tab rather than on the tablist. The container is a
                // grouping role and should not be focusable or handle keys
                // (S6852); the key always arrives at whichever tab has focus,
                // which is the element that should answer for it.
                onKeyDown={handleTabKeys}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* `hidden` rather than `&&`, so each panel keeps its DOM node and the
              tab pointing at it always has something to control. */}
          <div
            className="settingsCard"
            role="tabpanel"
            id="settings-panel-academic"
            aria-labelledby="settings-tab-academic"
            hidden={active !== "academic"}
          >
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

          <div
            className="settingsCard"
            role="tabpanel"
            id="settings-panel-calendar"
            aria-labelledby="settings-tab-calendar"
            hidden={active !== "calendar"}
          >
            <h2>Calendar</h2>
            <p className="muted small-text">
              These decide which gaps between your classes are worth offering as
              study time. They were under Academic until the groups existed.
            </p>

            <form className="loginForm" onSubmit={handleCalendarSubmit}>
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

              {calendarError && <p className="loginError">{calendarError}</p>}
              {calendarSaved && <p className="loginSuccess">Saved.</p>}

              <button type="submit" className="loginSubmit" disabled={savingCalendar}>
                {savingCalendar ? "Saving..." : "Save"}
              </button>
            </form>
          </div>

          {/* No form and no Save: both of these are their own dialogs that write
              for themselves. The same two are still reachable from the budget
              page, where you notice a category is wrong -- one setting with two
              doors, and one implementation behind both. */}
          <div
            className="settingsCard"
            role="tabpanel"
            id="settings-panel-financial"
            aria-labelledby="settings-tab-financial"
            hidden={active !== "financial"}
          >
            <h2>Financial</h2>
            <p className="muted small-text">
              How income divides between your accounts, and what you can file
              spending under.
            </p>

            <div className="settingsActions">
              <button
                type="button"
                className="calButton"
                onClick={() => setSplitOpen(true)}
                disabled={accounts.length === 0}
              >
                Income split
              </button>
              <button
                type="button"
                className="calButton"
                onClick={() => setCategoriesOpen(true)}
              >
                Edit categories
              </button>
            </div>

            {accounts.length === 0 && (
              <p className="muted small-text">
                The income split needs accounts to divide between. Add one on the
                Budget page and it appears here.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* `onSaved` is a real refetch, never a no-op. CategoriesModal fires it
          once per operation and stays open, reading every row from the prop it
          was handed -- so without this a deleted category would sit on screen
          and a rename would keep showing the old name. */}
      <IncomeSplitModal
        open={splitOpen}
        accounts={accounts}
        onClose={() => setSplitOpen(false)}
        onSaved={() => void loadMoneyBits()}
      />

      <CategoriesModal
        open={categoriesOpen}
        categories={categories}
        onClose={() => setCategoriesOpen(false)}
        onSaved={() => void loadMoneyBits()}
      />
    </div>
  );
}
