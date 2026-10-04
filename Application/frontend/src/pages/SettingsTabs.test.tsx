// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The settings tab strip.
 *
 * Three things are worth pinning here and only one of them is visual.
 *
 * **The tablist contract.** This is the first `role="tab"` in the app, so there
 * is no established pattern to inherit and nothing else to notice if it breaks.
 * A strip that looks right and announces nothing is the failure mode, and it is
 * invisible to anyone not using a screen reader.
 *
 * **One tab stop, with arrow keys.** The inactive tabs are `tabIndex={-1}` on
 * purpose. That is correct only if the arrows work -- otherwise a keyboard user
 * reaches the strip and can never change what it shows, which is worse than
 * three tab stops.
 *
 * **Unsaved edits survive a tab switch.** That was a decision, not a
 * consequence: the alternative was discarding them silently. It holds because
 * every field's state lives on the page rather than in the panel, which is easy
 * to undo by accident later.
 *
 * What this file cannot see: jsdom has no layout engine and no cascade, so the
 * gold rule on the selected tab, and the panels occupying the same space, are
 * not testable here. They are read off the built stylesheet.
 */

const refreshUser = vi.fn();
const updatePreferences = vi.fn().mockResolvedValue({});
const updateAcademicStatus = vi.fn().mockResolvedValue({});

const user = {
  id: "u1",
  name: "Test",
  email: "t@example.com",
  has_password: true,
  has_google: false,
  current_school_year: 3,
  current_semester: "Fall",
  first_year_calendar_year: 2024,
  suggested_first_year: null,
  preferences: {
    // Deliberately not whatever zone this test environment reports, so a browser
    // guess leaking into the field is visible rather than coincidentally right.
    timezone: "America/Vancouver",
    credit_target: 120,
    gpa_scale_enabled: true,
    default_target_grade: 85,
    study_day_start: "08:00:00",
    study_day_end: "22:00:00",
    min_free_block_minutes: 30,
  },
};

vi.mock("../app/auth/AuthContext", () => ({
  useAuth: () => ({ user, login: vi.fn(), refreshUser }),
}));

vi.mock("../services/currentUserClient", () => ({
  updateAcademicStatus: (...args: unknown[]) => updateAcademicStatus(...args),
  updatePreferences: (...args: unknown[]) => updatePreferences(...args),
}));

vi.mock("../services/authClient", () => ({
  setPassword: vi.fn().mockResolvedValue({ access_token: "t" }),
}));

vi.mock("../features/budget/api", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([
    { id: "a1", name: "Spending", kind: "spending", income_share: 60,
      archived: false, position: 0, counts_toward_net_worth: true,
      balance: 100, role_locked: false },
  ]),
  fetchCategories: vi.fn().mockResolvedValue([
    { id: "c1", name: "Groceries", archived: false, position: 0 },
  ]),
}));

// BlackoutsModal fetches its own data when it opens; stubbed so the dialog has
// something to resolve rather than an unhandled rejection.
vi.mock("../features/calender/api", () => ({
  fetchBlackouts: vi.fn().mockResolvedValue([]),
  createBlackout: vi.fn().mockResolvedValue({}),
  deleteBlackout: vi.fn().mockResolvedValue({}),
}));

import SettingsPage from "./SettingsPage";

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function tabs() {
  return screen.getAllByRole("tab");
}

/** The selected tab, read the way a screen reader would decide. */
function selected() {
  return tabs().filter((t) => t.getAttribute("aria-selected") === "true");
}

describe("the tab strip", () => {
  it("opens on Academic, with exactly one tab selected", () => {
    render(<SettingsPage />);

    expect(tabs()).toHaveLength(3);
    expect(selected()).toHaveLength(1);
    expect(selected()[0].textContent).toBe("Academic");
  });

  /**
   * The control for every "exactly one" and "is hidden" assertion in this file.
   * Without it they could all be passing against a strip whose clicks do
   * nothing -- which would satisfy "one tab selected" permanently.
   */
  it("changes which tab is selected when one is clicked", () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole("tab", { name: "Financial" }));

    expect(selected()).toHaveLength(1);
    expect(selected()[0].textContent).toBe("Financial");
  });

  it("shows one panel at a time, and hides the rest", () => {
    render(<SettingsPage />);

    const panels = () => ["academic", "calendar", "financial"].map(
      (id) => document.getElementById(`settings-panel-${id}`)!,
    );

    expect(panels().filter((p) => !p.hidden)).toHaveLength(1);
    expect(panels()[0].hidden).toBe(false);

    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    expect(panels().filter((p) => !p.hidden)).toHaveLength(1);
    expect(panels()[1].hidden).toBe(false);
    expect(panels()[0].hidden).toBe(true);
  });

  it("points each tab at the panel it controls, and each panel back", () => {
    render(<SettingsPage />);

    for (const tab of tabs()) {
      const panel = document.getElementById(tab.getAttribute("aria-controls")!);
      expect(panel, `${tab.textContent} controls nothing`).not.toBeNull();
      expect(panel!.getAttribute("aria-labelledby")).toBe(tab.id);
    }
  });
});

describe("keyboard", () => {
  it("is one tab stop: only the selected tab is reachable by Tab", () => {
    render(<SettingsPage />);

    expect(tabs().filter((t) => t.tabIndex === 0)).toHaveLength(1);
    expect(tabs().filter((t) => t.tabIndex === -1)).toHaveLength(2);
  });

  it("moves with the arrows, and takes focus with it", () => {
    render(<SettingsPage />);

    fireEvent.keyDown(selected()[0], { key: "ArrowRight" });

    expect(selected()[0].textContent).toBe("Calendar");
    expect(document.activeElement).toBe(selected()[0]);
  });

  it("wraps at both ends rather than stopping", () => {
    render(<SettingsPage />);

    // Left from the first lands on the last.
    fireEvent.keyDown(selected()[0], { key: "ArrowLeft" });
    expect(selected()[0].textContent).toBe("Financial");

    fireEvent.keyDown(selected()[0], { key: "ArrowRight" });
    expect(selected()[0].textContent).toBe("Academic");
  });

  it("jumps to the ends with Home and End", () => {
    render(<SettingsPage />);

    fireEvent.keyDown(selected()[0], { key: "End" });
    expect(selected()[0].textContent).toBe("Financial");

    fireEvent.keyDown(selected()[0], { key: "Home" });
    expect(selected()[0].textContent).toBe("Academic");
  });

  it("leaves other keys alone", () => {
    render(<SettingsPage />);

    fireEvent.keyDown(selected()[0], { key: "a" });

    expect(selected()[0].textContent).toBe("Academic");
  });
});

describe("switching tabs", () => {
  /**
   * The decision this phase was built around. The alternative was that leaving a
   * tab discarded what you had typed, which is the kind of loss nobody reports
   * because they assume they did it to themselves.
   */
  it("keeps unsaved edits when you leave and come back", () => {
    render(<SettingsPage />);

    const credits = screen.getByLabelText("Credits required for your degree");
    fireEvent.change(credits, { target: { value: "150" } });

    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));
    fireEvent.click(screen.getByRole("tab", { name: "Academic" }));

    expect(
      (screen.getByLabelText("Credits required for your degree") as HTMLInputElement).value,
    ).toBe("150");
  });
});

describe("each tab saves only its own preferences", () => {
  /**
   * Why this matters more than it looks: until the API took a real partial
   * patch, a request naming three preferences was parsed into all fourteen and
   * the merge wrote defaults over the rest. Two forms each sending their own
   * three keys is only safe because that was fixed -- so these two tests are the
   * frontend half of that fix, asserting the payloads are actually disjoint.
   */
  it("sends the academic keys and not the study window", async () => {
    render(<SettingsPage />);

    fireEvent.submit(screen.getByLabelText("Credits required for your degree").closest("form")!);

    await waitFor(() => expect(updatePreferences).toHaveBeenCalled());
    const sent = updatePreferences.mock.calls[0][1] as Record<string, unknown>;
    expect(Object.keys(sent).sort()).toEqual(
      ["credit_target", "default_target_grade", "gpa_scale_enabled"],
    );
  });

  it("sends the study window and the zone, and not the academic keys", async () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    fireEvent.submit(screen.getByLabelText("Shortest useful gap").closest("form")!);

    await waitFor(() => expect(updatePreferences).toHaveBeenCalled());
    const sent = updatePreferences.mock.calls[0][1] as Record<string, unknown>;
    expect(Object.keys(sent).sort()).toEqual(
      ["event_colors", "min_free_block_minutes", "study_day_end", "study_day_start", "timezone"],
    );
    expect(updateAcademicStatus).not.toHaveBeenCalled();
  });
});

describe("event colours", () => {
  function openCalendar() {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));
  }

  async function save() {
    fireEvent.submit(screen.getByLabelText("Shortest useful gap").closest("form")!);
    await waitFor(() => expect(updatePreferences).toHaveBeenCalled());
    return (updatePreferences.mock.calls[0][1] as Record<string, unknown>).event_colors;
  }

  afterEach(() => { delete (user.preferences as Record<string, unknown>).event_colors; });

  it("offers a colour for every kind, labelled", () => {
    openCalendar();
    for (const name of ["Lecture", "Lab", "Discussion", "Midterm", "Final", "Deadline", "Personal", "Shift"]) {
      expect(screen.getByLabelText(name, { selector: "input" })).toBeTruthy();
    }
  });

  it("saves nothing but an empty map when nothing was changed", async () => {
    openCalendar();
    expect(await save()).toEqual({});
  });

  it("saves a colour the user picked, and only that one", async () => {
    openCalendar();
    fireEvent.change(screen.getByLabelText("Lecture", { selector: "input" }), { target: { value: "#123456" } });
    expect(await save()).toEqual({ lecture: "#123456" });
  });

  it("shows the change on the sample before it is saved", () => {
    openCalendar();
    fireEvent.change(screen.getByLabelText("Lab", { selector: "input" }), { target: { value: "#123456" } });
    const sample = document.querySelector<HTMLElement>(".kindColorSample.calChip-lab")!;
    expect(sample.style.getPropertyValue("--kind-color")).toBe("#123456");
  });

  it("offers Default only for a changed kind, and Default removes it from the save", async () => {
    (user.preferences as Record<string, unknown>).event_colors = { lab: "#010203", final: "#040506" };
    openCalendar();

    expect(screen.queryByRole("button", { name: /default colour for Lecture/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /default colour for Lab/ }));
    expect(screen.queryByRole("button", { name: /default colour for Lab/ })).toBeNull();

    expect(await save()).toEqual({ final: "#040506" });
  });
});

describe("the time zone control", () => {
  /**
   * The trap this was written to avoid, and the only test here that matters much.
   *
   * Seeding the field from `Intl.DateTimeFormat().resolvedOptions().timeZone`
   * would mean that opening Settings anywhere else, touching nothing, and saving
   * the Calendar tab silently repointed every reminder the student has. A save
   * must not change something nobody asked it to -- which is the same fault the
   * preference-patch fix existed to stop, arriving by a different door.
   *
   * This test's own premise is asserted first, deliberately. It can only detect a
   * leaked guess while the environment's zone differs from the stored one --
   * `vitest.config.ts` pins `TZ: "America/Regina"` and the fixture stores
   * America/Vancouver, so today it does. If someone repins that TZ to match, this
   * test would quietly stop testing anything, and the assertion below turns that
   * into a failure rather than a false pass.
   */
  it("saves the stored zone when nothing was touched, not the browser's guess", async () => {
    const envZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    expect(envZone, "this test cannot detect a leaked guess unless the two differ")
      .not.toBe(user.preferences.timezone);

    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    fireEvent.submit(screen.getByLabelText("Shortest useful gap").closest("form")!);

    await waitFor(() => expect(updatePreferences).toHaveBeenCalled());
    const sent = updatePreferences.mock.calls[0][1] as Record<string, unknown>;
    expect(sent.timezone).toBe("America/Vancouver");
    expect(sent.timezone).not.toBe(envZone);
  });

  it("shows the stored zone as the selected option", () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    expect((screen.getByLabelText("Time zone") as HTMLSelectElement).value)
      .toBe("America/Vancouver");
  });

  /** The control: a select nobody can pick from would pass every test above. */
  it("sends a zone the user actually chose", async () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    fireEvent.change(screen.getByLabelText("Time zone"), {
      target: { value: "America/Halifax" },
    });
    fireEvent.submit(screen.getByLabelText("Shortest useful gap").closest("form")!);

    await waitFor(() => expect(updatePreferences).toHaveBeenCalled());
    expect((updatePreferences.mock.calls[0][1] as Record<string, unknown>).timezone)
      .toBe("America/Halifax");
  });

  it("offers a real list of zones, not just the fallback", () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    const options = (screen.getByLabelText("Time zone") as HTMLSelectElement).options;
    expect(options.length).toBeGreaterThan(8);
  });

  it("offers the device's zone as a suggestion, and applying it does not save", () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    // The stored zone differs from whatever this environment reports, so the
    // suggestion must be on offer.
    const suggestion = screen.getByRole("button", { name: /use it$/ });
    fireEvent.click(suggestion);

    expect((screen.getByLabelText("Time zone") as HTMLSelectElement).value)
      .not.toBe("America/Vancouver");
    expect(updatePreferences).not.toHaveBeenCalled();
  });

  it("stops offering the suggestion once it has been taken", () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    fireEvent.click(screen.getByRole("button", { name: /use it$/ }));

    expect(screen.queryByRole("button", { name: /use it$/ })).toBeNull();
  });
});

describe("blocked periods", () => {
  it("is reachable from the calendar tab", () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    expect(screen.getByRole("button", { name: "Blocked periods" })).toBeDefined();
  });

  it("opens its dialog", async () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Calendar" }));

    fireEvent.click(screen.getByRole("button", { name: "Blocked periods" }));

    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: "Blocked periods" })).toBeDefined(),
    );
  });
});

describe("the financial tab", () => {
  it("offers both dialogs once its data has loaded", async () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Financial" }));

    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Income split" }) as HTMLButtonElement).disabled)
        .toBe(false),
    );
    expect(screen.getByRole("button", { name: "Edit categories" })).toBeDefined();
  });

  /**
   * Asserted through the rename field rather than by text: a category's name is
   * an editable input in this dialog, so `getByText` finds nothing even when the
   * row is on screen. Worth knowing before writing the next test against it.
   */
  it("opens the categories dialog on the data Settings fetched", async () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Financial" }));

    fireEvent.click(screen.getByRole("button", { name: "Edit categories" }));

    await waitFor(() =>
      expect((screen.getByLabelText("Rename Groceries") as HTMLInputElement).value)
        .toBe("Groceries"),
    );
  });

  it("opens the income split dialog on the accounts Settings fetched", async () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Financial" }));

    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Income split" }) as HTMLButtonElement).disabled)
        .toBe(false),
    );
    fireEvent.click(screen.getByRole("button", { name: "Income split" }));

    await waitFor(() => expect(screen.getByLabelText(/Spending/)).toBeDefined());
  });
});
