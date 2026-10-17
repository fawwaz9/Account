// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EventOccurrence } from "../../calender/types";

/** The exam strip drops an exam once it is over, not at midnight. */

const { fetchAgenda } = vi.hoisted(() => ({ fetchAgenda: vi.fn() }));
vi.mock("../../calender/api", () => ({ fetchAgenda }));
// No Settings zone: the clock falls back to the browser's, which the fake timers set.
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1", preferences: {} } }) }));

import ExamStrip, { stillAhead } from "./ExamStrip";

function exam(over: Partial<EventOccurrence>): EventOccurrence {
  return {
    event_id: "e1", on_date: "2026-10-16", title: "Midterm", kind: "midterm", start_time: "10:30:00",
    end_time: "12:00:00", location: null, notes: null, course_id: null, course_code: "STAT_V 302", job_id: null,
    repeats: false, grade_id: null, ...over,
  };
}

const at = (date: string, minutes: number) => ({ date, minutes });

describe("stillAhead", () => {
  it("keeps today's exam until it ends", () => {
    expect(stillAhead(exam({}), at("2026-10-16", 11 * 60 + 59))).toBe(true);
    expect(stillAhead(exam({}), at("2026-10-16", 12 * 60))).toBe(false);
  });

  it("goes at the start when there is no end time", () => {
    const noEnd = exam({ end_time: null });
    expect(stillAhead(noEnd, at("2026-10-16", 10 * 60 + 29))).toBe(true);
    expect(stillAhead(noEnd, at("2026-10-16", 10 * 60 + 30))).toBe(false);
  });

  it("keeps an exam with no time all day", () => {
    expect(stillAhead(exam({ start_time: null, end_time: null }), at("2026-10-16", 23 * 60 + 59))).toBe(true);
  });

  it("keeps a later day's exam whatever the hour, and drops an earlier day's", () => {
    expect(stillAhead(exam({ on_date: "2026-10-17", end_time: "08:00:00" }), at("2026-10-16", 22 * 60))).toBe(true);
    expect(stillAhead(exam({ on_date: "2026-10-15", end_time: "23:00:00" }), at("2026-10-16", 60))).toBe(false);
  });
});

describe("the strip", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "setInterval", "clearTimeout", "clearInterval"] });
    fetchAgenda.mockResolvedValue([
      exam({ event_id: "morning" }),
      exam({ event_id: "later", on_date: "2026-10-20", course_code: "CPSC_V 304", start_time: "15:30:00", end_time: null }),
    ]);
  });
  afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks(); });

  async function show() {
    render(<MemoryRouter><ExamStrip /></MemoryRouter>);
    await act(async () => { await Promise.resolve(); });
  }

  it("leaves this morning's midterm off at 10pm", async () => {
    vi.setSystemTime(new Date(2026, 9, 16, 22, 0));
    await show();
    expect(screen.getByText("CPSC_V 304 Midterm")).toBeTruthy();
    expect(screen.queryByText("STAT_V 302 Midterm")).toBeNull();
  });

  it("shows it before it ends, and drops it on the minute it does", async () => {
    vi.setSystemTime(new Date(2026, 9, 16, 11, 59, 30));
    await show();
    expect(screen.getByText("STAT_V 302 Midterm")).toBeTruthy();
    await act(async () => { vi.advanceTimersByTime(60_000); });
    expect(screen.queryByText("STAT_V 302 Midterm")).toBeNull();
  });

  it("asks for the new day's exams once midnight passes", async () => {
    vi.setSystemTime(new Date(2026, 9, 16, 23, 59, 30));
    await show();
    expect(fetchAgenda).toHaveBeenLastCalledWith("u1", "2026-10-16", "2026-11-15");
    await act(async () => { vi.advanceTimersByTime(60_000); });
    expect(fetchAgenda).toHaveBeenLastCalledWith("u1", "2026-10-17", "2026-11-16");
  });
});
