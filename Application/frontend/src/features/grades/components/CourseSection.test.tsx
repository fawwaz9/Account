// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const api = { createCourse: vi.fn(), updateCourse: vi.fn() };
vi.mock("../api", () => ({
  createCourse: (...a: unknown[]) => api.createCourse(...a),
  updateCourse: (...a: unknown[]) => api.updateCourse(...a),
}));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import AddCourseModal from "./AddCourseModal";
import EditCourseModal from "./EditCourseModal";
import AttentionPanel from "./AttentionPanel";
import { CourseDetail, Semester } from "../types";

const course = {
  id: "c1", code: "CPSC 221", name: "Algorithms", semester: Semester.FALL, year: 2, credits: 3,
  required: true, professor: null, section: "101", final_grade: 0, target_grade: null,
  category_weights: {}, start_date: null, end_date: null, no_final: false, transfer_credit: false,
  archived: false, links: [], grades: [],
} as unknown as CourseDetail;

beforeEach(() => {
  api.createCourse.mockReset().mockResolvedValue({});
  api.updateCourse.mockReset().mockResolvedValue({});
});
afterEach(cleanup);

describe("the course section", () => {
  it("is optional when adding a course, and trimmed when given", async () => {
    render(<AddCourseModal open onClose={vi.fn()} onCourseAdded={vi.fn()} />);
    fireEvent.change(document.getElementById("course-code")!, { target: { value: "CPSC 221" } });
    fireEvent.change(document.getElementById("course-name")!, { target: { value: "Algorithms" } });
    fireEvent.change(document.getElementById("course-section")!, { target: { value: " L2B " } });
    fireEvent.submit(document.getElementById("course-code")!.closest("form")!);
    await waitFor(() => expect(api.createCourse).toHaveBeenCalledTimes(1));
    expect(api.createCourse.mock.calls[0][1].section).toBe("L2B");
  });

  it("is sent as none when left blank", async () => {
    render(<AddCourseModal open onClose={vi.fn()} onCourseAdded={vi.fn()} />);
    fireEvent.change(document.getElementById("course-code")!, { target: { value: "CPSC 221" } });
    fireEvent.change(document.getElementById("course-name")!, { target: { value: "Algorithms" } });
    fireEvent.submit(document.getElementById("course-code")!.closest("form")!);
    await waitFor(() => expect(api.createCourse).toHaveBeenCalledTimes(1));
    expect(api.createCourse.mock.calls[0][1].section).toBeNull();
  });

  it("starts the edit form from the course's section, and an edit keeps it", async () => {
    render(<EditCourseModal open course={course} onClose={vi.fn()} onCourseUpdated={vi.fn()} />);
    const input = document.getElementById("edit-course-section") as HTMLInputElement;
    expect(input.value).toBe("101");
    fireEvent.change(document.getElementById("edit-course-name")!, { target: { value: "Renamed" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(api.updateCourse).toHaveBeenCalledTimes(1));
    expect(api.updateCourse.mock.calls[0][2]).toMatchObject({ name: "Renamed", section: "101" });
  });

  it("is named in Attention when missing", () => {
    render(
      <MemoryRouter>
        <AttentionPanel userId="u1" items={[{
          kind: "missing_section", course_id: "c1", course_code: "CPSC 221",
          message: "no section recorded; a syllabus and schedule belong to one section",
        }]} />
      </MemoryRouter>,
    );
    expect(screen.getByText("No section")).toBeTruthy();
    expect(screen.getByText("CPSC 221")).toBeTruthy();
  });
});
