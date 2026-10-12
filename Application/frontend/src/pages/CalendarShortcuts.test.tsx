// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * N, the arrows and T on the Calendar page.
 *
 * Each must make the same call as the visible button it stands in for, so the
 * calendar hook is stubbed and the test watches those calls. Everything that
 * fetches is stubbed too: what is under test is the wiring, not the views.
 */

const step = vi.fn();
const setCursor = vi.fn();

vi.mock("../features/calender/hooks/useCalender", () => ({
  useCalender: () => ({
    view: "month", setView: vi.fn(), phone: false, views: ["week", "month"], label: "October 2026",
    cursor: "2026-10-03", setCursor, step,
    days: [], loading: false, error: null, reload: vi.fn(),
  }),
}));

vi.mock("../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", preferences: {} } }),
}));

vi.mock("../features/grades/api", () => ({ fetchCourses: vi.fn().mockResolvedValue([]) }));
vi.mock("../features/calender/api", () => ({
  deleteEvent: vi.fn(), fetchEvents: vi.fn(), skipOccurrence: vi.fn(),
}));

vi.mock("../features/calender/components/CalenderView", () => ({ default: () => null }));
vi.mock("../features/calender/components/WeekView", () => ({ default: () => null }));
vi.mock("../features/calender/components/TimeInsights", () => ({ default: () => null }));
vi.mock("../features/calender/components/TermTimeline", () => ({ default: () => null }));
vi.mock("../features/calender/components/BlackoutsModal", () => ({ default: () => null }));
vi.mock("../features/tasks/components/EditTaskModal", () => ({ default: () => null }));
vi.mock("../features/calender/components/EventModal", () => ({
  default: ({ open, defaultDate }: { open: boolean; defaultDate: string }) =>
    open ? <p>composing on {defaultDate}</p> : null,
}));

vi.mock("../shared/utils/dateUtils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../shared/utils/dateUtils")>()),
  today: () => "2026-10-03",
}));

import CalendarPage from "./CalendarPage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Calendar shortcuts", () => {
  it("N opens a new event on today", () => {
    render(<CalendarPage />);
    fireEvent.keyDown(document.body, { key: "n" });
    expect(screen.getByText("composing on 2026-10-03")).toBeTruthy();
  });

  it("the arrows step back and forward, as the header buttons do", () => {
    render(<CalendarPage />);
    fireEvent.keyDown(document.body, { key: "ArrowLeft" });
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    expect(step.mock.calls).toEqual([[-1], [1]]);
  });

  it("T jumps to today", () => {
    render(<CalendarPage />);
    fireEvent.keyDown(document.body, { key: "t" });
    expect(setCursor).toHaveBeenCalledWith("2026-10-03");
  });
});
