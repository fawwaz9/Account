// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { readSyllabus: vi.fn(), applySyllabus: vi.fn() };
vi.mock("./api", () => ({
  readSyllabus: (...a: unknown[]) => api.readSyllabus(...a),
  applySyllabus: (...a: unknown[]) => api.applySyllabus(...a),
}));

import SyllabusModal from "./SyllabusModal";
import { GradeCategory } from "../grades/types";

const parsed = {
  id: "p1",
  created_at: "2026-10-05T04:00:00",
  warnings: ["The weights add up to 90%, not 100%."],
  extract: {
    course_code: "CPSC 221", course_name: "Algorithms", professor: "Dr. Lee", multiple_schemes: false,
    assessments: [
      { name: "Assignments", category: GradeCategory.ASSIGNMENT, weight: 20, count: 3, due_date: null, date_tba: false },
      { name: "Midterm", category: GradeCategory.MIDTERM, weight: 30, count: 1, due_date: "2026-10-20", date_tba: false },
      { name: "Final", category: GradeCategory.FINAL, weight: 40, count: 1, due_date: null, date_tba: true },
    ],
  },
};

function show(onBuilt = vi.fn()) {
  render(<SyllabusModal userId="u1" onClose={vi.fn()} onBuilt={onBuilt} />);
  return onBuilt;
}

async function choose() {
  const file = new File(["%PDF-1.4"], "cpsc221.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Syllabus file"), { target: { files: [file] } });
  await screen.findByLabelText("Course code");
}

const create = () => screen.getByRole("button", { name: "Create course" }) as HTMLButtonElement;

beforeEach(() => {
  api.readSyllabus.mockReset();
  api.applySyllabus.mockReset();
  api.readSyllabus.mockResolvedValue(parsed);
});
afterEach(cleanup);

describe("SyllabusModal", () => {
  it("sends the file and lays out what was read, warnings first", async () => {
    show();
    await choose();
    const [userId, filename, mediaType, content] = api.readSyllabus.mock.calls[0];
    expect([userId, filename, mediaType]).toEqual(["u1", "cpsc221.pdf", "application/pdf"]);
    expect(atob(content)).toBe("%PDF-1.4");
    expect(screen.getByText("The weights add up to 90%, not 100%.")).toBeTruthy();
    expect((screen.getByLabelText("Course code") as HTMLInputElement).value).toBe("CPSC 221");
    expect((screen.getByLabelText("Weight of row 2") as HTMLInputElement).value).toBe("30");
  });

  it("will not create a course whose weights do not add up", async () => {
    show();
    await choose();
    expect(screen.getByText(/add up to 90% — they need to add up to 100%/)).toBeTruthy();
    expect(create().disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Weight of row 1"), { target: { value: "30" } });
    expect(screen.getByText("Weights add up to 100%")).toBeTruthy();
    expect(create().disabled).toBe(false);
  });

  it("marking a row TBA clears and locks its date", async () => {
    show();
    await choose();
    fireEvent.click(screen.getByLabelText("Row 2 is TBA"));
    const date = screen.getByLabelText("Date of row 2") as HTMLInputElement;
    expect(date.value).toBe("");
    expect(date.disabled).toBe(true);
  });

  it("a row can be removed, and an added row needs a name", async () => {
    show();
    await choose();
    fireEvent.change(screen.getByLabelText("Weight of row 1"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Add a row" }));
    expect(create().disabled).toBe(true); // the new row has no name
    fireEvent.click(screen.getByRole("button", { name: "Remove row 4" }));
    expect(create().disabled).toBe(false);
  });

  it("creates the course from what is on screen, and says so while it works", async () => {
    let finish: (value: unknown) => void = () => {};
    api.applySyllabus.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const onBuilt = show();
    await choose();
    fireEvent.change(screen.getByLabelText("Weight of row 1"), { target: { value: "30" } });
    fireEvent.change(screen.getByLabelText("Course code"), { target: { value: "CPSC 221A" } });
    fireEvent.click(create());
    expect(screen.getByRole("button", { name: "Creating…" })).toBeTruthy();
    finish({ course_id: "c9", grades_created: 5, fields_total: 20, fields_changed: 2 });
    await waitFor(() => expect(onBuilt).toHaveBeenCalledWith("c9"));
    const [, parseId, body] = api.applySyllabus.mock.calls[0];
    expect(parseId).toBe("p1");
    expect(body.course_code).toBe("CPSC 221A");
    expect(body.professor).toBe("Dr. Lee");
    expect(body.assessments.map((a: { weight: number }) => a.weight)).toEqual([30, 30, 40]);
  });

  it("carries the section read from the syllabus, editable, and blank as none", async () => {
    api.readSyllabus.mockResolvedValue({ ...parsed, extract: { ...parsed.extract, section: "101" } });
    api.applySyllabus.mockResolvedValue({ course_id: "c9", grades_created: 5, fields_total: 20, fields_changed: 0 });
    show();
    await choose();
    expect((screen.getByLabelText("Section") as HTMLInputElement).value).toBe("101");
    fireEvent.change(screen.getByLabelText("Weight of row 1"), { target: { value: "30" } });
    fireEvent.change(screen.getByLabelText("Section"), { target: { value: " 102 " } });
    fireEvent.click(create());
    await waitFor(() => expect(api.applySyllabus).toHaveBeenCalledTimes(1));
    expect(api.applySyllabus.mock.calls[0][2].section).toBe("102");

    cleanup();
    api.applySyllabus.mockClear();
    api.readSyllabus.mockResolvedValue(parsed);  // a syllabus that names no section
    show();
    await choose();
    expect((screen.getByLabelText("Section") as HTMLInputElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("Weight of row 1"), { target: { value: "30" } });
    fireEvent.click(create());
    await waitFor(() => expect(api.applySyllabus).toHaveBeenCalledTimes(1));
    expect(api.applySyllabus.mock.calls[0][2].section).toBeNull();
  });

  it("says why a syllabus couldn't be read, or a course couldn't be made", async () => {
    api.readSyllabus.mockRejectedValueOnce(new Error("That's today's limit for reading syllabi."));
    show();
    fireEvent.change(screen.getByLabelText("Syllabus file"), {
      target: { files: [new File(["x"], "s.pdf", { type: "application/pdf" })] },
    });
    expect((await screen.findByRole("alert")).textContent).toContain("today's limit");

    api.applySyllabus.mockRejectedValue(new Error("You already have a course CPSC 221"));
    fireEvent.change(screen.getByLabelText("Syllabus file"), {
      target: { files: [new File(["x"], "s.pdf", { type: "application/pdf" })] },
    });
    await screen.findByLabelText("Course code");
    fireEvent.change(screen.getByLabelText("Weight of row 1"), { target: { value: "30" } });
    fireEvent.click(create());
    expect((await screen.findByRole("alert")).textContent).toBe("You already have a course CPSC 221");
  });
});

describe("SyllabusModal: prerequisites (Phase 2 item 5)", () => {
  const withRules = {
    ...parsed,
    extract: {
      ...parsed.extract,
      assessments: parsed.extract.assessments.map((a) => (a.name === "Final" ? { ...a, weight: 50 } : a)),
      prerequisites: { rule: {}, text: "CPSC 210 and MATH 200", note: "Third-year standing",
                       sentence: "Pre-reqs: CPSC 210, MATH 200." },
      corequisites: null,
    },
  };

  it("shows what the syllabus says, editable, with its own words", async () => {
    api.readSyllabus.mockResolvedValue(withRules);
    show();
    await choose();
    expect((screen.getByLabelText("Prerequisites") as HTMLInputElement).value).toBe("CPSC 210 and MATH 200");
    expect(screen.getByText("Pre-reqs: CPSC 210, MATH 200.")).toBeTruthy();
    expect(screen.queryByLabelText("Co-requisites")).toBeNull();
  });

  it("files what you confirm", async () => {
    api.readSyllabus.mockResolvedValue(withRules);
    api.applySyllabus.mockResolvedValue({ course_id: "c9", grades_created: 5, fields_total: 1, fields_changed: 0 });
    show();
    await choose();
    fireEvent.change(screen.getByLabelText("Prerequisites"), { target: { value: "CPSC 213" } });
    fireEvent.click(create());
    await waitFor(() => expect(api.applySyllabus).toHaveBeenCalled());
    const body = api.applySyllabus.mock.calls[0][2];
    expect(body.prerequisites).toEqual({ text: "CPSC 213", note: "Third-year standing" });
    expect(body.corequisites).toBeUndefined();
  });

  it("files nothing for a field you clear", async () => {
    api.readSyllabus.mockResolvedValue(withRules);
    api.applySyllabus.mockResolvedValue({ course_id: "c9", grades_created: 5, fields_total: 1, fields_changed: 0 });
    show();
    await choose();
    fireEvent.change(screen.getByLabelText("Prerequisites"), { target: { value: "  " } });
    fireEvent.click(create());
    await waitFor(() => expect(api.applySyllabus).toHaveBeenCalled());
    expect(api.applySyllabus.mock.calls[0][2].prerequisites).toBeUndefined();
  });
});
