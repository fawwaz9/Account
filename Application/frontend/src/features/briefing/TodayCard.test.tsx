// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";

const api = { fetchDigest: vi.fn() };
vi.mock("./api", () => ({ fetchDigest: (...a: unknown[]) => api.fetchDigest(...a) }));

import TodayCard, { clock } from "./TodayCard";
import { Digest } from "./types";

/**
 * Phase 4 item 6, redrawn for the big screen (owner's sketch, 2026-11-07): the day's
 * schedule as a table, then the briefing's own overdue, at-risk and exam lines.
 */

const TEXT = [
  "Friday, November 6.",
  "Today: CPSC_V 320 lecture 9am–10am (CHBE 101); Jumuah 1:20pm–2pm.",
  "Due today: Checkpoint 5 (STAT_V 302).",
  "Overdue: 1 task — Reading 4.",
  "At risk: Lab 3 (in 2 days) — about 1h short at your usual pace.",
  "Exam: CPSC_V 320 midterm in 3 days — 2 open tasks, about 2h 30m.",
  "This week: 36h 25m booked, 2 tasks due.",
].join("\n");

function digest(over: Partial<Digest> = {}): Digest {
  return {
    on_date: "2026-11-06",
    events: [
      { title: "CPSC 320 lecture", kind: "lecture", start_time: "09:00:00", end_time: "10:00:00",
        location: "CHBE 101", course_code: "CPSC_V 320" },
      { title: "Jumuah", kind: "personal", start_time: "13:20:00", end_time: "14:00:00",
        location: null, course_code: null },
    ],
    due_today: [{ title: "Checkpoint 5", course_code: "STAT_V 302", due_date: "2026-11-06", due_time: null,
      estimated_minutes: null }],
    overdue: [], overdue_count: 1, exams: [], at_risk: [],
    week: { booked_minutes: 2185, estimated_minutes: 0, tasks_due: 2 },
    free_minutes_today: 0, longest_free_start: null, longest_free_minutes: 0,
    text: TEXT,
    ...over,
  };
}

beforeEach(() => { api.fetchDigest.mockReset(); });
afterEach(cleanup);

describe("TodayCard", () => {
  it("lists the day's events, then the tasks due, with when and where", async () => {
    api.fetchDigest.mockResolvedValue(digest());
    render(<TodayCard userId="u1" />);

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").map((row) =>
      within(row).getAllByRole("cell").map((cell) => cell.textContent));
    expect(rows).toEqual([
      ["CPSC_V 320", "9am – 10am", "CHBE 101"],
      ["Jumuah", "1:20pm – 2pm", ""],
      ["Checkpoint 5", "due today", "STAT_V 302"],
    ]);
    expect(api.fetchDigest).toHaveBeenCalledWith("u1");
  });

  it("puts the day in the heading", async () => {
    api.fetchDigest.mockResolvedValue(digest());
    render(<TodayCard userId="u1" />);
    const heading = await screen.findByRole("heading", { name: /^Today/ });
    expect(heading.textContent).toMatch(/Nov/);
    expect(heading.textContent).toMatch(/6/);
  });

  it("keeps only the warnings from the briefing's lines, marked", async () => {
    api.fetchDigest.mockResolvedValue(digest());
    render(<TodayCard userId="u1" />);

    const list = await screen.findByRole("list", { name: "Needs attention" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Overdue: 1 task — Reading 4.",
      "At risk: Lab 3 (in 2 days) — about 1h short at your usual pace.",
      "Exam: CPSC_V 320 midterm in 3 days — 2 open tasks, about 2h 30m.",
    ]);
    expect(screen.getByText(/^Overdue:/).className).toContain("todayLineWarn");
    expect(screen.getByText(/^Exam:/).className).toContain("todayLineExam");
    expect(screen.queryByText(/^This week:/)).toBeNull();
  });

  it("says when the day is empty, and shows no warning list without warnings", async () => {
    api.fetchDigest.mockResolvedValue(digest({ events: [], due_today: [], text: "Friday, November 6." }));
    render(<TodayCard userId="u1" />);
    expect(await screen.findByText("Nothing on the calendar today.")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Needs attention" })).toBeNull();
  });

  it("renders nothing when the digest can't be read", async () => {
    api.fetchDigest.mockRejectedValue(new Error("down"));
    const { container } = render(<TodayCard userId="u1" />);
    await waitFor(() => expect(api.fetchDigest).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});

describe("clock", () => {
  it("writes times as the briefing does", () => {
    expect([clock("00:00:00"), clock("09:00"), clock("10:30:00"), clock("12:00:00"), clock("23:05:00")])
      .toEqual(["12am", "9am", "10:30am", "12pm", "11:05pm"]);
  });
});
