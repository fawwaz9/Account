import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../app/auth/AuthContext";
import { setPassword } from "../services/authClient";
import { updateAcademicStatus, updatePreferences } from "../services/currentUserClient";
import { fetchAccounts, fetchCategories, updateAccount } from "../features/budget/api";
import { COUNTED_HELP } from "../features/budget/counting";
import { Account, SpendCategory } from "../features/budget/types";
import IncomeSplitModal from "../features/budget/components/IncomeSplitModal";
import BlackoutsModal from "../features/calender/components/BlackoutsModal";
import EventColors from "../features/calender/components/EventColors";
import { KindColors } from "../features/calender/kindColors";
import { chooseCashTipAccount } from "../features/jobs/api";
import HelpTip from "../shared/components/HelpTip";
import NotificationsSetting from "../features/notifications/NotificationsSetting";
import CategoriesModal from "../features/budget/components/CategoriesModal";
import "../styles/login.css";
// The two budget modals reached from the Financial tab style their rows from
// budget.css, and nothing else here imports it. In a production build this would
// not matter -- `cssCodeSplit: false` concatenates every stylesheet into one --
// but the dev server injects CSS per imported module, so without this those rows
// render unstyled on /settings until /budget has been visited.
import "../styles/budget.css";
import { PHONE_QUERY, useMediaQuery } from "../shared/hooks/useMediaQuery";

/** "08:00" from the API's "08:00:00", for a time input; the fallback when unset. */
function clockValue(value: unknown, fallback: string): string {
  return typeof value === "string" ? value.slice(0, 5) : fallback;
}

/** The server's default zone, repeated so an unset preference shows the zone actually applied. */
const DEFAULT_ZONE = "America/Regina";

/** Zones offered when the browser cannot list its own: Canada's, plus UTC. */
const FALLBACK_ZONES = [
  "America/St_Johns", "America/Halifax", "America/Toronto", "America/Winnipeg",
  "America/Regina", "America/Edmonton", "America/Vancouver", "UTC",
] as const;

/** Every zone the browser knows, or the fallback list. */
function supportedTimeZones(): readonly string[] {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] };
  try {
    const zones = intl.supportedValuesOf?.("timeZone");
    return zones && zones.length > 0 ? zones : FALLBACK_ZONES;
  } catch {
    return FALLBACK_ZONES;
  }
}

/** The browser's zone, offered as a suggestion but never applied. */
function guessedZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

/** Settings tabs in reading order; Academic comes first and is the default. */
const TABS = [
  { id: "academic", label: "Academic" },
  { id: "calendar", label: "Calendar" },
  { id: "financial", label: "Financial" },
] as const;

/** One of the tab ids. */
type TabId = (typeof TABS)[number]["id"];

/**
 * Settings: account, password and notifications, then the Academic, Calendar and Financial tabs.
 * Each tab saves only its own preferences; on a phone, Sign out lives here.
 */
export default function SettingsPage() {
  const { user, login, refreshUser, logout } = useAuth();
  // On a phone the header has no Sign out; the profile icon brings you here,
  // and this is where it lives instead.
  const phone = useMediaQuery(PHONE_QUERY);

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
  const [examBuffer, setExamBuffer] = useState(String(user?.preferences?.exam_buffer_hours ?? 12));
  // Stored value only. Seeding this from `guessedZone()` would mean that
  // opening Settings in another city silently repointed every reminder on the
  // next Calendar save -- a save changing something nobody asked it to, which
  // is the fault the preference-patch fix existed to stop.
  const [zone, setZone] = useState(user?.preferences?.timezone ?? DEFAULT_ZONE);
  const [colors, setColors] = useState<KindColors>(user?.preferences?.event_colors ?? {});
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
  // ?tab=financial opens on that tab -- the Jobs page's held-tip warning links
  // here. Read from window.location once, at mount, rather than a router hook:
  // it is only ever an entry point, and the page then owns the tab itself.
  const [active, setActive] = useState<TabId>(() => initialTab());
  const tablistRef = useRef<HTMLDivElement>(null);

  // What the Financial tab's two modals need. Two GETs rather than `useBudget`,
  // which returns these alongside six other reads and a `runRecurring` write --
  // a cost the budget page is right to pay and a settings page is not.
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [tipAccount, setTipAccount] = useState<string>(user?.preferences?.cash_tip_account_id ?? "");
  const [savingTip, setSavingTip] = useState(false);
  const [tipMessage, setTipMessage] = useState<string | null>(null);
  const [tipError, setTipError] = useState<string | null>(null);
  // Which accounts count (D39): the one being saved, and what happened.
  const [countingId, setCountingId] = useState<string | null>(null);
  const [countMessage, setCountMessage] = useState<string | null>(null);
  const [countError, setCountError] = useState<string | null>(null);
  const [categories, setCategories] = useState<SpendCategory[]>([]);
  const [splitOpen, setSplitOpen] = useState(false);
  const [categoriesOpen, setCategoriesOpen] = useState(false);
  const [blackoutsOpen, setBlackoutsOpen] = useState(false);

  // Neither depends on state, and the zone list runs to a few hundred
  // entries, so both are read once per render rather than per option.
  const zones = supportedTimeZones();
  const guess = guessedZone();

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
    setExamBuffer(String(user.preferences?.exam_buffer_hours ?? 12));
    setZone(user.preferences?.timezone ?? DEFAULT_ZONE);
    setColors(user.preferences?.event_colors ?? {});
    setTipAccount(user.preferences?.cash_tip_account_id ?? "");
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
        timezone: zone,
        study_day_start: studyStart,
        study_day_end: studyEnd,
        min_free_block_minutes: Number(minBlock),
        exam_buffer_hours: Number(examBuffer),
        // The whole map, always: the API replaces it, so a kind put back to its
        // default is absent here and therefore removed there.
        event_colors: colors,
      });
      await refreshUser();
      setCalendarSaved(true);
    } catch (err) {
      setCalendarError(err instanceof Error ? err.message : "Could not save your settings");
    } finally {
      setSavingCalendar(false);
    }
  }

  const activeAccounts = accounts.filter((account) => !account.archived);
  // Chosen, but archived or deleted since: tips are being held, and that needs
  // saying on the page, because it changes what you should do.
  const tipAccountGone =
    tipAccount !== "" && accounts.length > 0 && !activeAccounts.some((account) => account.id === tipAccount);

  /**
   * Choose where cash tips go. Saves on change, like the tab's other controls
   * that write for themselves -- and says what happened, because choosing can
   * file tips that were waiting, which is money moving into an account.
   */
  /** Tick or untick one account: in or out of net worth and every figure (D39). */
  async function handleCounted(account: Account, counts: boolean) {
    if (!user) return;
    setCountingId(account.id);
    setCountMessage(null);
    setCountError(null);
    try {
      await updateAccount(user.id, account.id, { counts_toward_net_worth: counts });
      setCountMessage(counts ? `${account.name} counts again.` : `${account.name} no longer counts.`);
      await loadMoneyBits();
    } catch (err) {
      setCountError(err instanceof Error ? err.message : "Could not save that");
    } finally {
      setCountingId(null);
    }
  }

  async function handleTipAccount(next: string) {
    if (!user) return;
    const previous = tipAccount;
    setTipAccount(next);
    setTipMessage(null);
    setTipError(null);
    setSavingTip(true);
    try {
      const result = await chooseCashTipAccount(user.id, next || null);
      const name = activeAccounts.find((account) => account.id === next)?.name;
      setTipMessage(
        result.filed > 0 && name
          ? `Saved. ${result.filed} held ${result.filed === 1 ? "tip" : "tips"} filed into ${name}.`
          : "Saved.",
      );
      await refreshUser();
    } catch (err) {
      setTipAccount(previous);
      setTipError(err instanceof Error ? err.message : "Could not save that");
    } finally {
      setSavingTip(false);
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
            {user && <NotificationsSetting userId={user.id} />}
            {/* Said out loud, as the vision requires of any analytics here, but
                behind the (?) rather than as ambient text: it answers "what is
                this", which is what the owner asked those to be for. */}
            <div className="settingsRow">
              <span className="settingsLabel">Usage counts</span>
              <span>
                On{" "}
                <HelpTip label="What usage counts are">
                  Each day, which parts of the app you opened and how many things you added
                  in each -- a count, nothing more. No pages, no content, nothing you typed.
                  They are only ever read as totals across everyone, to see which parts of
                  the app are worth building on, and they are deleted with your account.
                </HelpTip>
              </span>
            </div>
            {phone && (
              <button type="button" className="calButton phoneSignOut" onClick={logout}>
                Sign out
              </button>
            )}
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
            <div className="headingWithTip">
              <h2>Academic</h2>
              <HelpTip label="What the academic settings decide">
                Your current term decides which courses count as past, current or
                future, which is what the Grades page groups by. The first-year
                anchor is what gives each term real dates.
              </HelpTip>
            </div>

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
                <HelpTip label="What the first-year anchor is for">
                  A school year is 1, 2, 3 — not a calendar year. This is what gives each
                  term real dates, so leaving it blank means nothing that measures a term
                  can say when it ran.
                </HelpTip>
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
                <HelpTip label="What the default target does">
                  Used for any course that has not been given a target of its own.
                  Changing it moves every course still on the default.
                </HelpTip>
              </div>

              <div className="settingsToggle">
                <input
                  id="gpa-enabled"
                  type="checkbox"
                  checked={gpaEnabled}
                  onChange={(event) => setGpaEnabled(event.target.checked)}
                />
                <span className="labelWithTip">
                  <label htmlFor="gpa-enabled">Show CGPA</label>
                  <HelpTip label="Why CGPA is optional">
                    UBC does not put a GPA on transcripts, so this is off by default. Turn
                    it on if you need the figure for an application.
                  </HelpTip>
                </span>
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
            <div className="headingWithTip">
              <h2>Calendar</h2>
              <HelpTip label="What the calendar settings decide">
                Which gaps between your classes are worth offering as study time.
                The window sets the hours, and the minimum block decides how short
                a gap stops being useful.
              </HelpTip>
            </div>

            <form className="loginForm" onSubmit={handleCalendarSubmit}>
              {/* First in the panel because it is the one setting here that can
                  make another figure wrong rather than merely unhelpful. */}
              <div className="loginField">
                {/* The mark is a sibling of the label, not inside it. A control's
                    accessible name is computed from its label's contents, so a
                    nested button would append its own name to the select's and
                    leave it announced as "Time zone What the time zone affects". */}
                <span className="labelWithTip">
                  <label htmlFor="timezone">Time zone</label>
                  <HelpTip label="What the time zone affects">
                    Reminders fire on this clock, not the server&apos;s. It also
                    decides which calendar day a task was finished on, so whether
                    Tasks calls your work early or late is measured against it.
                    Evening work in the wrong zone reads as a day late.
                  </HelpTip>
                </span>
                <select
                  id="timezone"
                  className="loginInput"
                  value={zone}
                  onChange={(event) => setZone(event.target.value)}
                >
                  {/* A stored zone the browser cannot list would otherwise vanish
                      from the control and be replaced on the next save. */}
                  {!zones.includes(zone) && <option value={zone}>{zone}</option>}
                  {zones.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
                {/* Offered, never applied -- the same treatment the first-year
                    field gets, and for the same reason: getting this wrong moves
                    every reminder you have, and it is the student who knows where
                    they are. */}
                {guess !== null && guess !== zone && (
                  <button
                    type="button"
                    className="courseLinkAdd"
                    onClick={() => setZone(guess)}
                  >
                    This device says {guess} — use it
                  </button>
                )}
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
                <HelpTip label="What the study window does">
                  Free blocks are only offered between these hours, so a gap at seven in
                  the morning is not suggested unless you said it counts.
                </HelpTip>
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
                <span className="loginHint">Minutes</span>
                <HelpTip label="What the minimum block is for">
                  A gap shorter than this is walking time rather than study time, so it is
                  left out of the free blocks the calendar offers.
                </HelpTip>
              </div>

              <div className="loginField">
                <label htmlFor="exam-buffer">Keep clear before an exam</label>
                <input
                  id="exam-buffer"
                  className="loginInput"
                  type="number"
                  min={0}
                  max={48}
                  value={examBuffer}
                  onChange={(event) => setExamBuffer(event.target.value)}
                  required
                />
                <span className="loginHint">Hours</span>
                <HelpTip label="What keeping clear before an exam does">
                  A shift that ends less than this long before a midterm or final is flagged on the
                  Jobs page and the calendar. 0 flags only a shift that runs into the exam itself.
                </HelpTip>
              </div>

              {/* Inside the form, but no part of its Save: the dialog writes for
                  itself. Both controls here are type="button" (the HelpTip's
                  included), so neither can submit the form -- a plain <button>
                  in a form submits it, which would save the calendar settings
                  as a side effect of opening a dialog. Still on the Calendar
                  page too, where you notice a reading break while looking at the
                  week it ruins. The mark sits beside the button, never inside
                  it: a button cannot contain a button. */}
              <div className="settingsActions">
                <button
                  type="button"
                  className="calButton"
                  onClick={() => setBlackoutsOpen(true)}
                >
                  Blocked periods
                </button>
                <HelpTip label="What blocked periods do">
                  Weeks when classes do not run. Entered once and applied to
                  everything attached to a course, so a reading break does not have
                  to be cancelled on each of six of them. Your own events, standing
                  payments and repeating tasks carry on.
                </HelpTip>
              </div>

              <fieldset className="loginField kindColorField">
                <legend className="labelWithTip">
                  <span>Event colours</span>
                  <HelpTip label="What event colours change">
                    How each kind of event is drawn on the calendar, in both the
                    month and the week. Midterms and finals keep their heavier bar
                    and bold title, so exam weeks stand out in any colour.
                  </HelpTip>
                </legend>
                <EventColors colors={colors} onChange={setColors} />
              </fieldset>

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
            <div className="headingWithTip">
              <h2>Financial</h2>
              <HelpTip label="What the financial settings decide">
                How income divides between your accounts when you record a deposit,
                and which categories you can file spending under.
              </HelpTip>
            </div>

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

            {/* One switch per account for net worth and every analytic (D39).
                Saved on each tick, like the cash-tip picker below; the same
                words as the account's edit dialog. */}
            {activeAccounts.length > 0 && (
              <fieldset className="countedAccounts">
                <legend className="labelWithTip">
                  <span>Counted accounts</span>
                  <HelpTip label="What counting an account means">{COUNTED_HELP}</HelpTip>
                </legend>
                {activeAccounts.map((account) => (
                  <label key={account.id} className="settingsToggle">
                    <input
                      type="checkbox"
                      checked={account.counts_toward_net_worth !== false}
                      disabled={countingId !== null}
                      onChange={(event) => void handleCounted(account, event.target.checked)}
                    />
                    {account.name}
                  </label>
                ))}
                {countError && <p className="loginError" role="alert">{countError}</p>}
                {countMessage && <p className="loginSuccess" role="status">{countMessage}</p>}
              </fieldset>
            )}

            <div className="loginField">
              <span className="labelWithTip">
                <label htmlFor="cash-tip-account">Cash tips go to</label>
                <HelpTip label="Where cash tips go">
                  A cash tip is in your pocket, not the bank, so it goes into this
                  one account instead of being split like a paycheque. Until you
                  choose, tips are recorded on the shift but kept out of your
                  budget. Tips already in your budget stay where they are.
                </HelpTip>
              </span>
              <select
                id="cash-tip-account"
                className="loginInput"
                value={tipAccountGone ? "" : tipAccount}
                onChange={(event) => void handleTipAccount(event.target.value)}
                disabled={savingTip}
              >
                <option value="">Not chosen</option>
                {activeAccounts.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </select>
              {tipAccountGone && (
                <p className="loginError">
                  The account chosen for cash tips is no longer available, so new
                  tips are being held. Choose another.
                </p>
              )}
              {tipError && <p className="loginError">{tipError}</p>}
              {tipMessage && <p className="loginSuccess" role="status">{tipMessage}</p>}
            </div>
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

      {/* `onSaved` genuinely can do nothing here, unlike the two above. Those
          render rows from a prop this page owns, so they need a refetch to stop
          showing what was just deleted. This one fetches its own blackouts when
          it opens and refetches them itself after a write, and Settings holds no
          calendar data for a stale copy to live in. */}
      <BlackoutsModal
        open={blackoutsOpen}
        onClose={() => setBlackoutsOpen(false)}
        onSaved={() => undefined}
      />
    </div>
  );
}

/** The tab named in ?tab=, if it is one of ours; Academic otherwise. */
function initialTab(): TabId {
  const named = new URLSearchParams(window.location.search).get("tab");
  return TABS.some((tab) => tab.id === named) ? (named as TabId) : "academic";
}

