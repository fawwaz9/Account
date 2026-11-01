// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const api = { searchCatalogue: vi.fn(), planNextTerm: vi.fn() };
vi.mock("../../features/grades/api", () => ({
  searchCatalogue: (...a: unknown[]) => api.searchCatalogue(...a),
  planNextTerm: (...a: unknown[]) => api.planNextTerm(...a),
}));
const AUTH = { user: { id: "u1" } };
vi.mock("../../app/auth/AuthContext", () => ({ useAuth: () => AUTH }));

import NextTermPage, { professorLink } from "./NextTermPage";

/** Phase 4 item 12: candidate courses, past students' figures added up, a link out for instructors. */

const CPSC = { id: "k1", campus: "UBCV", subject: "CPSC", number: "221", title: "Algorithms", credits: 4 };

beforeEach(() => {
  api.searchCatalogue.mockReset().mockResolvedValue([CPSC]);
  api.planNextTerm.mockReset().mockResolvedValue({
    courses: [{ catalogue_id: "k1", code: "CPSC 221", campus: "UBCV", title: "Algorithms", credits: 4,
      intel: { hours_answers: 7, hours_median: 12, difficulty_answers: 7, difficulty_mean: 4.1, clarity_answers: null,
        clarity_mean: null, again_answers: null, again_share: null } }],
    total_hours: 12, courses_with_hours: 1, total_credits: 4, mean_difficulty: 4.1, missing: [], floor: 5,
    assumptions: ["Hours are the median weekly hours past students reported."],
  });
});
afterEach(cleanup);

describe("NextTermPage", () => {
  it("adds a catalogue course and shows the combination's hours", async () => {
    render(<MemoryRouter><NextTermPage /></MemoryRouter>);

    fireEvent.change(screen.getByRole("searchbox", { name: "Search the catalogue" }), { target: { value: "cpsc 2" } });
    fireEvent.click(await screen.findByRole("button", { name: /CPSC 221/ }));

    await waitFor(() => expect(api.planNextTerm).toHaveBeenCalledWith("u1", ["k1"]));
    expect(await screen.findByText("12 hours a week")).toBeTruthy();
  });

  it("links out to RateMyProfessors only once a name is typed", async () => {
    render(<MemoryRouter><NextTermPage /></MemoryRouter>);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search the catalogue" }), { target: { value: "cpsc 2" } });
    fireEvent.click(await screen.findByRole("button", { name: /CPSC 221/ }));
    const field = await screen.findByRole("textbox", { name: "Instructor for CPSC 221" });

    expect(screen.queryByRole("link", { name: /RateMyProfessors/ })).toBeNull();
    fireEvent.change(field, { target: { value: "Jane Doe" } });

    const link = screen.getByRole("link", { name: /RateMyProfessors/ }) as HTMLAnchorElement;
    expect(link.href).toBe(professorLink("Jane Doe"));
    expect(link.rel).toContain("noopener");
  });

  it("builds the search URL from the name alone, encoded", () => {
    expect(professorLink("  Ana María ")).toBe("https://www.ratemyprofessors.com/search/professors?q=Ana%20Mar%C3%ADa");
  });
});
