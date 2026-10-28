// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = { fetchClassFigures: vi.fn() };
vi.mock("../api", () => ({
  fetchClassFigures: (...a: unknown[]) => api.fetchClassFigures(...a),
}));

import ClassFigures, { bandLabel, filledBands, intelLines } from "./ClassFigures";
import { ClassFigures as Figures, CourseIntel, TermDistribution } from "../types";

/** Phase 3 items 3 and 5: past students' shared grades and reviews on the course page (D11). */

const fall: TermDistribution = {
  term_code: "2024W1", term_label: "Fall 2024", contributors: 7, median_bucket: 80,
  bands: [{ bucket: 70, contributors: 2 }, { bucket: 80, contributors: 4 }, { bucket: 90, contributors: 1 }],
};
const winter: TermDistribution = {
  term_code: "2023W2", term_label: "Winter 2024", contributors: 5, median_bucket: 60,
  bands: [{ bucket: 60, contributors: 5 }],
};

function figures(over: Partial<Figures> = {}): Figures {
  return {
    course_key: "CPSC 221", floor: 5, distributions: [fall, winter], your_grade: 74.25, your_bucket: 70, intel: null,
    ...over,
  };
}

function show() {
  return render(<ClassFigures userId="u1" courseId="c1" nonce={0} />);
}

// Braced: a hook that returns the mock would have it called as a teardown.
beforeEach(() => { api.fetchClassFigures.mockReset(); });
afterEach(cleanup);

describe("bandLabel and filledBands", () => {
  it("reads bands the way a transcript does", () => {
    expect([bandLabel(0), bandLabel(50), bandLabel(80), bandLabel(95)]).toEqual(
      ["Below 50", "50–54", "80–84", "95–100"]);
  });

  it("fills the gaps between held bands with zero, so the shape is honest", () => {
    const term = { ...fall, bands: [{ bucket: 0, contributors: 1 }, { bucket: 60, contributors: 4 }] };
    expect(filledBands(term)).toEqual([
      { bucket: 0, contributors: 1 }, { bucket: 50, contributors: 0 }, { bucket: 55, contributors: 0 },
      { bucket: 60, contributors: 4 },
    ]);
  });
});

const intel: CourseIntel = {
  hours_answers: 12, hours_median: 9, difficulty_answers: 11, difficulty_mean: 3.6,
  clarity_answers: null, clarity_mean: null, again_answers: 6, again_share: 70,
};

describe("intelLines", () => {
  it("reads each figure above the floor, with how many gave it, and skips the rest", () => {
    expect(intelLines(intel)).toEqual([
      { label: "Hours a week", value: "about 9", from: 12 },
      { label: "Difficulty", value: "3.6 / 5", from: 11 },
      { label: "Would take it again", value: "70%", from: 6 },
    ]);
  });
});

describe("ClassFigures", () => {
  it("shows what past students' reviews say above the grades", async () => {
    api.fetchClassFigures.mockResolvedValue(figures({ intel }));
    show();
    expect(await screen.findByText("Hours a week")).toBeTruthy();
    expect(screen.getByText("Would take it again").nextSibling?.textContent).toBe("70% (6)");
    expect(screen.queryByText("Instructor clarity")).toBeNull();
    expect(screen.getByRole("list", { name: "Grades in Fall 2024" })).toBeTruthy();
  });

  it("with reviews but no grades yet, says only the grades are waiting", async () => {
    api.fetchClassFigures.mockResolvedValue(figures({ intel, distributions: [] }));
    show();
    expect(await screen.findByText("Grades shown once 5 students in a finished term have shared theirs.")).toBeTruthy();
  });

  it("shows the newest term's bands, its median and where you sit", async () => {
    api.fetchClassFigures.mockResolvedValue(figures());
    show();
    expect(await screen.findByText(/Fall 2024 · 7 students · median 80–84 · you: 74.3%/)).toBeTruthy();
    const list = screen.getByRole("list", { name: "Grades in Fall 2024" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((row) => row.textContent)).toEqual(["70–742 you", "75–790", "80–844 median", "85–890", "90–941"]);
  });

  it("switches to an older term", async () => {
    api.fetchClassFigures.mockResolvedValue(figures());
    show();
    fireEvent.change(await screen.findByRole("combobox", { name: "Term" }), { target: { value: "2023W2" } });
    expect(await screen.findByRole("list", { name: "Grades in Winter 2024" })).toBeTruthy();
  });

  it("says what it is waiting for below the floor", async () => {
    api.fetchClassFigures.mockResolvedValue(figures({ distributions: [] }));
    show();
    expect(await screen.findByText("Shown once 5 students in a finished term have shared their grade.")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("leaves out 'you' for an unmarked course", async () => {
    api.fetchClassFigures.mockResolvedValue(figures({ distributions: [fall], your_grade: null, your_bucket: null }));
    show();
    expect(await screen.findByText("Fall 2024 · 7 students · median 80–84")).toBeTruthy();
    expect(screen.queryByText(/you/)).toBeNull();
  });

  it("renders nothing for a course that can't be counted", async () => {
    api.fetchClassFigures.mockResolvedValue(figures({ course_key: null, distributions: [] }));
    const { container } = show();
    await waitFor(() => expect(api.fetchClassFigures).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("renders nothing when the read fails", async () => {
    api.fetchClassFigures.mockRejectedValue(new Error("down"));
    const { container } = show();
    await waitFor(() => expect(api.fetchClassFigures).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});
