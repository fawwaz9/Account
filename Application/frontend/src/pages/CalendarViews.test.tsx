// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The phone views (next.md, Calendar): one day and three days in place of the
 * week, three days by default, arrows and swipes a page at a time.
 *
 * The real calendar hook runs here, against a controllable `matchMedia` and
 * stubbed fetches, so what is tested is the default, the switch, the window
 * actually fetched and what a rotation does -- not a stub's idea of them.
 */

const { fetchAgenda } = vi.hoisted(() => ({ fetchAgenda: vi.fn() }));

vi.mock("../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", preferences: {} } }),
}));
vi.mock("../features/calender/api", () => ({
  fetchAgenda, deleteEvent: vi.fn(), fetchEvents: vi.fn(), skipOccurrence: vi.fn(),
}));
vi.mock("../features/tasks/api", () => ({ fetchTasks: vi.fn().mockResolvedValue([]) }));
vi.mock("../features/tasks/sharing", () => ({ fetchSharedTasks: vi.fn().mockResolvedValue([]) }));
vi.mock("../features/calender/sharing", () => ({ fetchSharedEvents: vi.fn().mockResolvedValue([]) }));
vi.mock("../features/grades/api", () => ({ fetchCourses: vi.fn().mockResolvedValue([]) }));

vi.mock("../features/calender/components/CalenderView", () => ({
  default: () => <div data-testid="grid">month</div>,
}));
vi.mock("../features/calender/components/WeekView", () => ({
  default: ({ days }: { days: { date: string }[] }) => <div data-testid="grid">{days.length} days</div>,
}));
vi.mock("../features/calender/components/TimeInsights", () => ({ default: () => null }));
vi.mock("../features/calender/components/TermTimeline", () => ({ default: () => null }));
vi.mock("../features/calender/components/BlackoutsModal", () => ({ default: () => null }));
vi.mock("../features/calender/components/EventModal", () => ({ default: () => null }));
vi.mock("../features/tasks/components/EditTaskModal", () => ({ default: () => null }));
vi.mock("../features/jobs/components/ShiftConflictsPanel", () => ({ default: () => null }));

vi.mock("../shared/utils/dateUtils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../shared/utils/dateUtils")>()),
  // A Saturday, so a three-day window starting here crosses into the next week.
  today: () => "2026-10-03",
}));

import CalendarPage from "./CalendarPage";

/** A `matchMedia` whose answer the test sets, and which tells its listeners. */
function fakeScreen(phone: boolean) {
  const listeners = new Set<() => void>();
  const list = {
    get matches() { return phone; },
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  window.matchMedia = vi.fn(() => list) as unknown as typeof window.matchMedia;
  return {
    resize(next: boolean) {
      phone = next;
      act(() => { listeners.forEach((fn) => fn()); });
    },
  };
}

function tabs() {
  return screen.getAllByRole("button").filter((button) => button.className.includes("calViewTab"));
}

function pressed() {
  return tabs().find((tab) => tab.getAttribute("aria-pressed") === "true")?.textContent;
}

function heading() {
  return screen.getByRole("heading", { level: 2 }).textContent;
}

function swipe(dx: number) {
  const grid = screen.getByTestId("grid");
  fireEvent.touchStart(grid, { touches: [{ clientX: 200, clientY: 300 }] });
  fireEvent.touchEnd(grid, { changedTouches: [{ clientX: 200 + dx, clientY: 305 }] });
}

const original = window.matchMedia;

beforeEach(() => {
  fetchAgenda.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.matchMedia = original;
});

describe("on a desktop", () => {
  it("offers the week and the month, opening on the week", async () => {
    fakeScreen(false);
    render(<CalendarPage />);

    expect(tabs().map((tab) => tab.textContent)).toEqual(["Week", "Month"]);
    expect(pressed()).toBe("Week");
    expect(heading()).toBe("28 Sep – 4 Oct 2026");
    expect(screen.getByLabelText("Previous week")).toBeTruthy();
    await waitFor(() => expect(fetchAgenda).toHaveBeenCalledWith("u1", "2026-09-28", "2026-10-04"));
  });

  it("behaves as it did where there is no matchMedia at all", () => {
    // @ts-expect-error -- removed to stand in for jsdom and very old browsers
    delete window.matchMedia;
    render(<CalendarPage />);
    expect(tabs().map((tab) => tab.textContent)).toEqual(["Week", "Month"]);
  });

  it("ignores a swipe", () => {
    fakeScreen(false);
    render(<CalendarPage />);
    swipe(-120);
    expect(heading()).toBe("28 Sep – 4 Oct 2026");
  });
});

describe("on a phone", () => {
  it("offers a day, three days and the month -- no week -- opening on three days from today", async () => {
    fakeScreen(true);
    render(<CalendarPage />);

    expect(tabs().map((tab) => tab.textContent)).toEqual(["Day", "3 day", "Month"]);
    expect(pressed()).toBe("3 day");
    expect(heading()).toBe("3 – 5 Oct 2026");
    expect(screen.getByTestId("grid").textContent).toBe("3 days");
    await waitFor(() => expect(fetchAgenda).toHaveBeenCalledWith("u1", "2026-10-03", "2026-10-05"));
  });

  it("moves three days a press, and names it so", () => {
    fakeScreen(true);
    render(<CalendarPage />);

    fireEvent.click(screen.getByLabelText("Next 3 days"));
    expect(heading()).toBe("6 – 8 Oct 2026");
    fireEvent.click(screen.getByLabelText("Previous 3 days"));
    fireEvent.click(screen.getByLabelText("Previous 3 days"));
    expect(heading()).toBe("30 Sep – 2 Oct 2026");
  });

  it("shows one day, a day a press", async () => {
    fakeScreen(true);
    render(<CalendarPage />);

    fireEvent.click(screen.getByRole("button", { name: "Day" }));
    expect(heading()).toBe("Sat 3 Oct 2026");
    expect(screen.getByTestId("grid").textContent).toBe("1 days");
    fireEvent.click(screen.getByLabelText("Next day"));
    expect(heading()).toBe("Sun 4 Oct 2026");
    await waitFor(() => expect(fetchAgenda).toHaveBeenLastCalledWith("u1", "2026-10-04", "2026-10-04"));
  });

  it("steps forward on a swipe to the left and back on one to the right", () => {
    fakeScreen(true);
    render(<CalendarPage />);

    swipe(-120);
    expect(heading()).toBe("6 – 8 Oct 2026");
    swipe(120);
    swipe(120);
    expect(heading()).toBe("30 Sep – 2 Oct 2026");
  });

  it("swipes the month too", () => {
    fakeScreen(true);
    render(<CalendarPage />);

    fireEvent.click(screen.getByRole("button", { name: "Month" }));
    swipe(-120);
    expect(heading()).toBe("November 2026");
  });
});

describe("crossing the breakpoint", () => {
  it("turns three days into the week and back, keeping the date", () => {
    const screenSize = fakeScreen(true);
    render(<CalendarPage />);
    fireEvent.click(screen.getByLabelText("Next 3 days"));
    expect(heading()).toBe("6 – 8 Oct 2026");

    screenSize.resize(false);
    expect(pressed()).toBe("Week");
    expect(heading()).toBe("5 – 11 Oct 2026");

    screenSize.resize(true);
    expect(pressed()).toBe("3 day");
    expect(heading()).toBe("6 – 8 Oct 2026");
  });

  it("keeps the month on either side", () => {
    const screenSize = fakeScreen(false);
    render(<CalendarPage />);
    fireEvent.click(screen.getByRole("button", { name: "Month" }));

    screenSize.resize(true);
    expect(pressed()).toBe("Month");
    screenSize.resize(false);
    expect(pressed()).toBe("Month");
  });
});
