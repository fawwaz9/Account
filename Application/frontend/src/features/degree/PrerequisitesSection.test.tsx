// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

const api = { fetchPrerequisiteSummaries: vi.fn() };
vi.mock("./api", () => ({
  fetchPrerequisiteSummaries: (...a: unknown[]) => api.fetchPrerequisiteSummaries(...a),
}));
// The opened course shows these two; each has tests of its own.
const opened = vi.hoisted(() => ({ onChanged: null as null | (() => void) }));
vi.mock("../grades/components/CatalogueLine", () => ({
  default: ({ courseId }: { courseId: string }) => <p>catalogue line for {courseId}</p>,
}));
vi.mock("../grades/components/PrerequisitesPanel", () => ({
  STATUS_WORDS: { met: "Met", on_track: "On track", not_met: "Not met" },
  default: ({ courseId, onChanged }: { courseId: string; onChanged: () => void }) => {
    opened.onChanged = onChanged;
    return <p>rules for {courseId}</p>;
  },
}));

import PrerequisitesSection from "./PrerequisitesSection";
import { PrerequisiteSummary } from "./api";

/** Prerequisites on the degree audit, moved off the course page (owner, 2026-11-07). */

function row(over: Partial<PrerequisiteSummary>): PrerequisiteSummary {
  return { course_id: "c", code: "CPSC 221", name: "Data structures", planned: false, status: "met", linked: true, ...over };
}

beforeEach(() => { api.fetchPrerequisiteSummaries.mockReset(); opened.onChanged = null; });
afterEach(cleanup);

describe("PrerequisitesSection", () => {
  it("lists the courses to look at, and keeps the rest behind a summary", async () => {
    api.fetchPrerequisiteSummaries.mockResolvedValue([
      row({ course_id: "a", code: "CPSC 221", status: "not_met" }),
      row({ course_id: "b", code: "CPSC 213", status: "on_track", planned: true }),
      row({ course_id: "c", code: "MATH 200", status: "met" }),
      row({ course_id: "d", code: "ENGL 110", status: null, linked: false }),
    ]);
    render(<PrerequisitesSection userId="u1" />);
    const look = await screen.findByRole("list", { name: "Courses to look at" });
    expect(within(look).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "CPSC 221 · Data structuresNot met",
      "CPSC 213 · Data structuresOn track · planned",
    ]);
    const rest = screen.getByRole("list", { name: "Other courses" });
    expect(within(rest).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "MATH 200 · Data structuresMet",
      "ENGL 110 · Data structuresNo rule recorded · not linked to the catalogue",
    ]);
    expect(screen.getByText("Your other courses (2)")).toBeTruthy();
  });

  it("opens a course to its catalogue link and rules, and refreshes when a rule changes", async () => {
    api.fetchPrerequisiteSummaries.mockResolvedValue([row({ course_id: "a", status: "not_met" })]);
    render(<PrerequisitesSection userId="u1" />);
    const toggle = await screen.findByRole("button", { name: "CPSC 221 · Data structures" });
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("catalogue line for a")).toBeTruthy();
    expect(screen.getByText("rules for a")).toBeTruthy();

    api.fetchPrerequisiteSummaries.mockResolvedValue([row({ course_id: "a", status: "met" })]);
    opened.onChanged?.();
    expect(await screen.findByText("Every course you're taking or planning has its prerequisites met, or none recorded."))
      .toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "CPSC 221 · Data structures" }));
    expect(screen.queryByText("rules for a")).toBeNull();
  });

  it("says when nothing needs a look", async () => {
    api.fetchPrerequisiteSummaries.mockResolvedValue([row({ status: "met" })]);
    render(<PrerequisitesSection userId="u1" />);
    expect(await screen.findByText(/has its prerequisites met, or none recorded/)).toBeTruthy();
  });

  it("renders nothing with no courses under way or planned, or when the read fails", async () => {
    api.fetchPrerequisiteSummaries.mockResolvedValue([]);
    const { container } = render(<PrerequisitesSection userId="u1" />);
    await vi.waitFor(() => expect(api.fetchPrerequisiteSummaries).toHaveBeenCalled());
    expect(container.textContent).toBe("");
    cleanup();
    api.fetchPrerequisiteSummaries.mockRejectedValue(new Error("down"));
    const failed = render(<PrerequisitesSection userId="u1" />);
    await vi.waitFor(() => expect(api.fetchPrerequisiteSummaries).toHaveBeenCalledTimes(2));
    expect(failed.container.textContent).toBe("");
  });
});
