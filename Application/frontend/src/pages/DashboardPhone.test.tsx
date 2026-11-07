// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The phone dashboard, from the owner's sketch: no greeting; a grades card, a
 * money card in whole dollars, and this week with its exams and shifts. The
 * checklist and the survey stay while they apply; the desktop's other extras
 * do not come along.
 */

const SUMMARY = {
  total_courses: 26, cumulative_average: 88.38, semester_average: 93.89, cgpa: 4.05, credits_completed: 66,
  best_course: { course_code: "CPSC 210", average: 97 }, weakest_course: { course_code: "MATH 200", average: 80 },
};
const state = {
  user: { id: "u1", name: "Sample", current_school_year: 3 as number | null, current_semester: "Fall" as string | null,
    preferences: { timezone: "America/Regina" } },
  dashboard: { summary: SUMMARY as unknown, loading: false, error: null as string | null },
  budget: {
    accounts: [{ balance: 10 }] as unknown[],
    summary: { total_actual: 3937.6, total_planned: 4450, by_category: [{ category_name: "Rent", actual: 1800 }] } as unknown,
    totalBalance: 19023.2, error: null as string | null, loaded: true,
  },
  time: {
    blocks: [
      { on_date: "2026-10-17", starts_at: "08:00:00", minutes: 780 },
      { on_date: "2026-10-16", starts_at: "14:00:00", minutes: 420 },
    ],
    load: { booked_minutes: 1660, task_count: 7, estimated_minutes: 120 } as unknown,
    loaded: true,
    counts: { exams: 2, shifts: 3 } as { exams: number; shifts: number } | null,
  },
};

vi.mock("../app/auth/AuthContext", () => ({ useAuth: () => ({ user: state.user }) }));
vi.mock("../features/grades/hooks/useDashboard", () => ({ useDashboard: () => state.dashboard }));
vi.mock("../features/budget/hooks/useBudgetGlance", () => ({ useBudgetGlance: () => state.budget }));
vi.mock("../features/calender/hooks/useTimeGlance", () => ({ useTimeGlance: () => state.time }));
vi.mock("../features/calender/hooks/useWorkloadForecast", () => ({
  useWorkloadForecast: () => ({ taskCount: 7 }),
}));
vi.mock("../features/calender/components/WorkloadHeadline", () => ({
  default: () => <p>Next 7 days</p>,
}));
vi.mock("../features/survey/DisappointmentQuestion", () => ({ default: () => <p>survey</p> }));
// The Today card has tests of its own; here it only needs to be there.
vi.mock("../features/briefing/TodayCard", () => ({
  default: () => <section aria-label="Today"><h2>Today</h2></section>,
}));
vi.mock("../features/onboarding/GetStarted", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../features/onboarding/GetStarted")>()),
  default: () => <h2>Get started</h2>,
}));

import Dashboard from "./Dashboard";

const original = window.matchMedia;
function onScreen(phone: boolean) {
  window.matchMedia = vi.fn(() => ({
    matches: phone, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

function show() {
  return render(<MemoryRouter><Dashboard /></MemoryRouter>);
}

function card(name: string) {
  return within(screen.getByRole("region", { name }));
}

beforeEach(() => {
  onScreen(true);
  state.user = { ...state.user, current_school_year: 3, current_semester: "Fall" };
  state.time = { ...state.time, counts: { exams: 2, shifts: 3 } };
});
afterEach(() => { cleanup(); window.matchMedia = original; });

describe("the phone dashboard", () => {
  it("says no welcome", () => {
    show();
    expect(screen.queryByRole("heading", { name: /Welcome/ })).toBeNull();
  });

  it("shows the grades card with this term's average under the term's name, and credits completed", () => {
    show();
    const grades = card("Grades");
    for (const text of ["88.38", "Average", "4.05", "CGPA", "26", "Courses", "93.89", "Year 3 Fall", "66",
      "Credits completed"]) {
      expect(grades.getByText(text)).toBeTruthy();
    }
  });

  it("names the term generically when no term is set", () => {
    state.user = { ...state.user, current_school_year: null, current_semester: null };
    show();
    expect(card("Grades").getByText("This term")).toBeTruthy();
  });

  it("rounds the money to whole dollars", () => {
    show();
    const money = card("Money");
    expect(money.getByText("$3,938")).toBeTruthy();
    expect(money.getByText("$512")).toBeTruthy();
    expect(money.getByText("$19,023")).toBeTruthy();
    expect(money.queryByText(/\.\d\d/)).toBeNull();
  });

  it("shows this week with its exams and shifts, and the two longest free stretches", () => {
    show();
    const week = card("This week");
    expect(week.getByText("27h 40m")).toBeTruthy();
    expect(week.getByText("Tasks due")).toBeTruthy();
    expect(week.getByText("Exams")).toBeTruthy();
    expect(week.getByText("Shifts")).toBeTruthy();
    expect(week.getByText("Free time: 13h Sat, 7h Fri")).toBeTruthy();
  });

  it("drops the exam and shift figures, and nothing else, when the calendar could not be read", () => {
    state.time = { ...state.time, counts: null };
    show();
    const week = card("This week");
    expect(week.queryByText("Exams")).toBeNull();
    expect(week.queryByText("Shifts")).toBeNull();
    expect(week.getByText("27h 40m")).toBeTruthy();
  });

  it("keeps the survey, and leaves out the desktop's other extras", () => {
    show();
    expect(screen.getByText("survey")).toBeTruthy();
    expect(screen.queryByText("Next 7 days")).toBeNull();
    expect(screen.queryByText(/Strongest/)).toBeNull();
    expect(screen.queryByText(/Biggest this month/)).toBeNull();
    expect(screen.queryByText(/Estimated work/)).toBeNull();
  });

  it("keeps the checklist while a step is unfinished", () => {
    state.dashboard = { ...state.dashboard, summary: { ...SUMMARY, total_courses: 0 } };
    show();
    expect(screen.getByRole("heading", { name: "Get started" })).toBeTruthy();
    state.dashboard = { ...state.dashboard, summary: SUMMARY };
  });
});

describe("the desktop dashboard (the owner's big-screen sketch, 2026-11-07)", () => {
  beforeEach(() => onScreen(false));

  /** Each figure's value and label, in order, from one card. */
  function figures(name: string) {
    return card(name).getAllByText((_, el) => el?.classList.contains("statBlock") ?? false)
      .map((block) => block.textContent);
  }

  it("welcomes by name, then three cards in a row and Today", () => {
    const { container } = show();
    expect(screen.getByRole("heading", { name: "Welcome, Sample" })).toBeTruthy();
    const rows = container.querySelectorAll(".dashCards");
    expect([...rows[0].children].map((el) => el.getAttribute("aria-label"))).toEqual(["Grades", "This week", "Money"]);
    expect([...rows[1].children].map((el) => el.getAttribute("aria-label"))).toEqual(["Today"]);
  });

  it("shows the grades card as average, this term, CGPA and credits", () => {
    show();
    expect(figures("Grades")).toEqual(["88.38Average", "93.89Year 3 Fall", "4.05CGPA", "66Credits completed"]);
  });

  it("shows this week with exams, shifts and the longest free stretches", () => {
    show();
    expect(card("This week").getByRole("heading", { name: "This week" })).toBeTruthy();
    expect(figures("This week")).toEqual(["27h 40mBooked", "7Tasks due", "2Exams", "3Shifts"]);
    expect(card("This week").getByText(/^Free time: 13h/)).toBeTruthy();
  });

  it("titles the money card with the month, in whole dollars", () => {
    show();
    const month = new Date().toLocaleDateString(undefined, { month: "long" });
    expect(card("Money").getByRole("heading", { name: month })).toBeTruthy();
    expect(figures("Money")).toEqual(["$3,938Spent", "$512Left", "$19,023Net worth"]);
  });

  it("leaves out the old extras", () => {
    show();
    expect(screen.queryByText(/Strongest/)).toBeNull();
    expect(screen.queryByText(/Biggest this month/)).toBeNull();
    expect(screen.queryByText("Next 7 days")).toBeNull();
    expect(screen.queryByText(/Estimated work/)).toBeNull();
    expect(screen.queryByText("Courses")).toBeNull();
  });
});
