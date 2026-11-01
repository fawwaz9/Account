// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const api = { fetchCorrelations: vi.fn() };
vi.mock("./api", () => ({ fetchCorrelations: (...a: unknown[]) => api.fetchCorrelations(...a) }));

import CorrelationsCard from "./CorrelationsCard";

/** Phase 4 item 8: exertion against finished work; quiet until eight weeks; never a cause. */

const READY = {
  ready: true, weeks_of_both: 10, needed_weeks: 8,
  caution: "Weeks that move together aren't proof that one causes the other.",
  correlations: [{
    key: "tasks", body_label: "Exertion points", academic_label: "Tasks finished", weeks: 10, coefficient: 0.5,
    strength: "moderate", reading: "A moderate link across 10 weeks: in weeks you moved more, you tended to finish more tasks.",
    pairs: [{ week_start: "2026-10-19", body: 40, academic: 3 }, { week_start: "2026-10-26", body: 80, academic: 5 }],
  }],
};

beforeEach(() => { api.fetchCorrelations.mockReset(); });
afterEach(cleanup);

describe("CorrelationsCard", () => {
  it("reads each pair in words, with the caution", async () => {
    api.fetchCorrelations.mockResolvedValue(READY);
    render(<CorrelationsCard userId="u1" />);

    expect(await screen.findByText(/A moderate link across 10 weeks/)).toBeTruthy();
    expect(screen.getByText(/aren't proof/)).toBeTruthy();
    expect(screen.getByRole("img", { name: /10 weeks of exertion points against tasks finished/ })).toBeTruthy();
  });

  it("says how close it is before it has enough weeks", async () => {
    api.fetchCorrelations.mockResolvedValue({ ...READY, ready: false, weeks_of_both: 5, correlations: [] });
    render(<CorrelationsCard userId="u1" />);

    expect(await screen.findByText(/logged for 8 weeks: 5 so far/)).toBeTruthy();
    expect(screen.queryByText(/link across/)).toBeNull();
  });

  it("says nothing with neither room logged", async () => {
    api.fetchCorrelations.mockResolvedValue({ ...READY, ready: false, weeks_of_both: 0, correlations: [] });
    const { container } = render(<CorrelationsCard userId="u1" />);

    await waitFor(() => expect(api.fetchCorrelations).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});
