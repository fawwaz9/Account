// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import SemesterSummary from "./SemesterSummary";
import { UserGradeDashboard } from "../types";

/** Phase 4 D5: the cumulative average and CGPA including this term, beside the official pair. */

function dashboard(over: Partial<UserGradeDashboard> = {}): UserGradeDashboard {
  return {
    total_courses: 3, cumulative_average: 88.38, semester_average: 72, cgpa: 4.05,
    cumulative_average_including_term: 84.1, cgpa_including_term: 3.81,
    credits_completed: 60, credits_in_progress: 15, credits_required: 45, credits_elective: 15,
    credit_target: 120, attention: [], term_history: [], past_years: [], future_years: [],
    best_course: null, weakest_course: null, courses_needing_final_score: [],
    unfinished_categories_by_course: {},
    ...over,
  };
}

afterEach(cleanup);

describe("SemesterSummary", () => {
  it("shows the official pair unchanged, and the second pair under its own label", () => {
    render(<SemesterSummary summary={dashboard()} />);

    expect(screen.getByText("88.38%")).toBeTruthy();
    expect(screen.getByText("4.05")).toBeTruthy();

    const including = screen.getByLabelText("Including this term");
    expect(within(including).getByText("Including this term")).toBeTruthy();
    expect(within(including).getByText("84.1%")).toBeTruthy();
    expect(within(including).getByText("3.81")).toBeTruthy();
    // The official figures are not inside the labelled group.
    expect(within(including).queryByText("88.38%")).toBeNull();
  });

  it("hides the second pair when no current course has a mark", () => {
    render(<SemesterSummary summary={dashboard({ cumulative_average_including_term: null, cgpa_including_term: null })} />);

    expect(screen.queryByLabelText("Including this term")).toBeNull();
    expect(screen.getByText("88.38%")).toBeTruthy();
  });

  it("hides it against an older API that sends neither field", () => {
    const older = dashboard();
    delete older.cumulative_average_including_term;
    delete older.cgpa_including_term;

    render(<SemesterSummary summary={older} />);

    expect(screen.queryByLabelText("Including this term")).toBeNull();
  });

  it("shows the average without a CGPA when the GPA scale is off", () => {
    render(<SemesterSummary summary={dashboard({ cgpa: null, cgpa_including_term: null })} />);

    const including = screen.getByLabelText("Including this term");
    expect(within(including).getByText("84.1%")).toBeTruthy();
    expect(within(including).queryByText("CGPA")).toBeNull();
  });

  it("explains what it counts", () => {
    render(<SemesterSummary summary={dashboard()} />);

    fireEvent.click(screen.getByRole("button", { name: "What including this term means" }));

    expect(screen.getByRole("note").textContent).toContain("running average");
  });
});
