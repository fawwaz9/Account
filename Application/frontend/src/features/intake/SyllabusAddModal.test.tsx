// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { readSyllabus: vi.fn(), previewAdd: vi.fn(), addToCourse: vi.fn() };
vi.mock("./api", () => ({
  readSyllabus: (...a: unknown[]) => api.readSyllabus(...a),
  previewAdd: (...a: unknown[]) => api.previewAdd(...a),
  addToCourse: (...a: unknown[]) => api.addToCourse(...a),
}));

import SyllabusAddModal from "./SyllabusAddModal";
import { GradeCategory } from "../grades/types";

const preview = {
  rows: [
    { name: "Assignments 1", category: GradeCategory.ASSIGNMENT, due_date: null, exists: true, matched: "Assignment 1" },
    { name: "Assignments 2", category: GradeCategory.ASSIGNMENT, due_date: null, exists: false, matched: null },
    { name: "Final exam", category: GradeCategory.FINAL, due_date: null, exists: false, matched: null },
  ],
  weight_notes: [{ category: GradeCategory.FINAL, syllabus: 40, course: 0 }],
  unweighted: [GradeCategory.FINAL],
  section_offer: "101",
};

function show(onAdded = vi.fn()) {
  render(<SyllabusAddModal userId="u1" courseId="c1" onClose={vi.fn()} onAdded={onAdded} />);
  return onAdded;
}

async function choose() {
  fireEvent.change(screen.getByLabelText("Syllabus file"), {
    target: { files: [new File(["%PDF-1.4"], "s.pdf", { type: "application/pdf" })] },
  });
  await screen.findByLabelText("Assessments from the syllabus");
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.readSyllabus.mockResolvedValue({ id: "p1" });
  api.previewAdd.mockResolvedValue(preview);
});
afterEach(cleanup);

describe("SyllabusAddModal", () => {
  it("offers only what the course lacks, and says what it already has", async () => {
    show();
    await choose();
    expect(api.previewAdd).toHaveBeenCalledWith("u1", "p1", "c1");
    expect(screen.getByText(/Assignments 1 · Assignment — already on the course as "Assignment 1"/)).toBeTruthy();
    expect(screen.queryByLabelText("Add Assignments 1")).toBeNull();
    expect((screen.getByLabelText("Add Assignments 2") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText(/this course has 0%\. Weights aren.t changed here/)).toBeTruthy();
    expect(screen.getByText(/won.t count until you set/)).toBeTruthy();
  });

  it("adds the ticked rows and the section, says what happened, and reloads the page", async () => {
    api.addToCourse.mockResolvedValue({ added: 1, skipped: 0, section_set: true });
    const onAdded = show();
    await choose();
    fireEvent.click(screen.getByLabelText("Add Final exam"));  // untick one
    fireEvent.click(screen.getByRole("button", { name: "Add 1 assessment" }));
    await waitFor(() => expect(api.addToCourse).toHaveBeenCalledTimes(1));
    const [, parseId, courseId, body] = api.addToCourse.mock.calls[0];
    expect([parseId, courseId]).toEqual(["p1", "c1"]);
    expect(body).toEqual({
      rows: [{ name: "Assignments 2", category: GradeCategory.ASSIGNMENT, due_date: null }],
      set_section: true,
    });
    expect((await screen.findByRole("status")).textContent).toContain("Added 1 assessment, and set the section");
    expect(onAdded).toHaveBeenCalledTimes(1);
  });

  it("will not send nothing", async () => {
    show();
    await choose();
    fireEvent.click(screen.getByLabelText("Add Assignments 2"));
    fireEvent.click(screen.getByLabelText("Add Final exam"));
    fireEvent.click(screen.getByLabelText(/Set this course.s section to 101/));
    expect((screen.getByRole("button", { name: "Add 0 assessments" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("says when reading or adding failed", async () => {
    api.readSyllabus.mockRejectedValueOnce(new Error("That's today's limit for reading syllabi."));
    show();
    fireEvent.change(screen.getByLabelText("Syllabus file"), {
      target: { files: [new File(["x"], "s.pdf", { type: "application/pdf" })] },
    });
    expect((await screen.findByRole("alert")).textContent).toContain("today's limit");
  });
});
