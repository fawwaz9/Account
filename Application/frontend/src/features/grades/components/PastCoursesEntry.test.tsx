// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const api = { createCourse: vi.fn() };
vi.mock("../api", () => ({ createCourse: (...a: unknown[]) => api.createCourse(...a) }));

import PastCoursesEntry from "./PastCoursesEntry";
import { CourseCard } from "./CourseList";
import { Course, Semester } from "../types";

/** Final-grade-only courses (owner, 2026-11-07): quick entry under Past Courses, and their card. */

const onAdded = vi.fn();
beforeEach(() => { api.createCourse.mockReset(); onAdded.mockReset(); });
afterEach(cleanup);

function openEntry() {
  render(<PastCoursesEntry userId="u1" onAdded={onAdded} />);
  fireEvent.click(screen.getByRole("button", { name: "Add past courses" }));
}

function fill(row: number, fields: Record<string, string>) {
  for (const [label, value] of Object.entries(fields)) {
    fireEvent.change(screen.getByLabelText(`Row ${row} ${label}`), { target: { value } });
  }
}

describe("PastCoursesEntry", () => {
  it("adds each typed row as a final-grade-only course, then closes", async () => {
    api.createCourse.mockResolvedValue({});
    openEntry();
    fill(1, { code: "CPSC 110", name: "Programming", year: "1", "final grade": "84" });
    fireEvent.click(screen.getByRole("button", { name: "Add row" }));
    fill(2, { code: "MATH 100", name: "Calculus", "final grade": "91.5" });
    fireEvent.click(screen.getByRole("button", { name: "Add row" }));  // left blank: skipped
    fireEvent.click(screen.getByRole("button", { name: "Add courses" }));

    await waitFor(() => expect(onAdded).toHaveBeenCalledTimes(1));
    expect(api.createCourse).toHaveBeenCalledTimes(2);
    const [userId, first] = api.createCourse.mock.calls[0];
    expect(userId).toBe("u1");
    expect(first).toMatchObject({
      code: "CPSC 110", name: "Programming", year: 1, semester: Semester.FALL, credits: 3, final_grade: 84,
      category_weights: {}, transfer_credit: false,
    });
    // No weights at all, so the course is final-grade-only (a partial match would accept any).
    expect(first.category_weights).toEqual({});
    expect(api.createCourse.mock.calls[1][1]).toMatchObject({ code: "MATH 100", year: 1, final_grade: 91.5 });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("checks rows before sending any, and says which is wrong", async () => {
    openEntry();
    fill(1, { code: "CPSC 110", name: "Programming" });
    fireEvent.click(screen.getByRole("button", { name: "Add courses" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Row 1: Final grade needs to be above 0 and at most 100.");
    expect(api.createCourse).not.toHaveBeenCalled();
  });

  it("keeps the rows the server refused, with its reason, and adds the rest", async () => {
    api.createCourse.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error("Course code already exists"));
    openEntry();
    fill(1, { code: "CPSC 110", name: "Programming", "final grade": "84" });
    fireEvent.click(screen.getByRole("button", { name: "Add row" }));
    fill(2, { code: "CPSC 121", name: "Logic", "final grade": "77" });
    fireEvent.click(screen.getByRole("button", { name: "Add courses" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Row 1: Course code already exists");
    expect(screen.getByText("Added 1 of 2. The rest weren't added:")).toBeTruthy();
    expect((screen.getByLabelText("Row 1 code") as HTMLInputElement).value).toBe("CPSC 121");
    expect(onAdded).toHaveBeenCalledTimes(1);
  });

  it("closes from Cancel or the ×, sending nothing", () => {
    openEntry();
    fireEvent.click(screen.getByRole("button", { name: "Close dialog" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Add past courses" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.createCourse).not.toHaveBeenCalled();
  });
});

function course(over: Partial<Course> = {}): Course {
  return {
    id: "c1", code: "CPSC 110", name: "Programming", year: 1, semester: Semester.FALL, credits: 3, required: true,
    professor: null, section: null, final_grade: 84, target_grade: null, category_weights: {}, average: null,
    start_date: null, end_date: null, no_final: false, transfer_credit: false, archived: false, links: [],
    letter_grade: "A-", grade_points: 3.7, term_bucket: "past", ...over,
  };
}

describe("a final-grade-only course card", () => {
  it("opens Edit Course instead of the page, and says what it is", () => {
    const onEdit = vi.fn();
    render(<MemoryRouter><CourseCard course={course({ final_only: true })} onEditFinalOnly={onEdit} /></MemoryRouter>);
    const card = screen.getByRole("button", { name: /CPSC 110/ });
    expect(card.className).toContain("courseBoxFinalOnly");
    expect(card.textContent).toContain("final only");
    fireEvent.click(card);
    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: "c1" }));
  });

  it("leaves an ordinary course's card as it was", () => {
    const onEdit = vi.fn();
    render(<MemoryRouter><CourseCard course={course({ final_only: false })} onEditFinalOnly={onEdit} /></MemoryRouter>);
    const card = screen.getByRole("button", { name: /CPSC 110/ });
    expect(card.className).toBe("courseBox");
    fireEvent.click(card);
    expect(onEdit).not.toHaveBeenCalled();
  });
});
