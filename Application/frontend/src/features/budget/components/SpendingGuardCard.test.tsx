// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchSpendingGuard: vi.fn(), allocateForCrunch: vi.fn(), dismissCrunchSuggestion: vi.fn() };
vi.mock("../api", () => ({
  fetchSpendingGuard: (...a: unknown[]) => api.fetchSpendingGuard(...a),
  allocateForCrunch: (...a: unknown[]) => api.allocateForCrunch(...a),
  dismissCrunchSuggestion: (...a: unknown[]) => api.dismissCrunchSuggestion(...a),
}));

import SpendingGuardCard, { loadWords } from "./SpendingGuardCard";

/** Phase 4 item 13: before a crunch week, your own past spikes; silent otherwise. */

const GUARD = {
  ready: true, crunch_weeks: 3, needed_crunch_weeks: 2,
  upcoming: { starts_on: "2099-11-02", days_away: 2, exams: 2, deadlines: 0, tasks: 5 },
  lifts: [{ category: "Delivery", crunch_weekly: 85, usual_weekly: 38, lift: 2.2, crunch_weeks: 3 }],
  note: "A heads-up, not a licence.",
};

beforeEach(() => { api.fetchSpendingGuard.mockReset(); });
afterEach(cleanup);

describe("SpendingGuardCard", () => {
  it("names the week, what's in it, and the categories that spike", async () => {
    api.fetchSpendingGuard.mockResolvedValue(GUARD);
    render(<SpendingGuardCard userId="u1" nonce={0} />);

    expect(await screen.findByText(/A heavy week from/)).toBeTruthy();
    expect(screen.getByText(/2 exams and 5 tasks/)).toBeTruthy();
    expect(screen.getByText("Delivery")).toBeTruthy();
    expect(screen.getByText(/2.2× over 3 crunch weeks/)).toBeTruthy();
    expect(screen.getByText("A heads-up, not a licence.")).toBeTruthy();
  });

  it.each([
    ["before it has learned enough", { ...GUARD, ready: false }],
    ["with no crunch week ahead", { ...GUARD, upcoming: null }],
    ["with nothing that spikes", { ...GUARD, lifts: [] }],
  ])("says nothing %s", async (_label, guard) => {
    api.fetchSpendingGuard.mockResolvedValue(guard);
    const { container } = render(<SpendingGuardCard userId="u1" nonce={0} />);

    await waitFor(() => expect(api.fetchSpendingGuard).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("lists a week's load in words", () => {
    expect(loadWords({ exams: 1, deadlines: 0, tasks: 0 })).toBe("1 exam");
    expect(loadWords({ exams: 2, deadlines: 3, tasks: 1 })).toBe("2 exams, 3 deadlines and 1 task");
  });
});

describe("SpendingGuardCard, setting aside", () => {
  const LIFTED = { ...GUARD, lifts: [{ ...GUARD.lifts[0], category_id: "cat1", set_aside: null, dismissed: false }] };

  beforeEach(() => {
    api.allocateForCrunch.mockReset().mockResolvedValue({ ...LIFTED, lifts: [{ ...LIFTED.lifts[0], set_aside: 85 }] });
    api.dismissCrunchSuggestion.mockReset().mockResolvedValue({ ...LIFTED, lifts: [{ ...LIFTED.lifts[0], dismissed: true }] });
  });

  it("sets the usual crunch-week amount aside for the week ahead", async () => {
    api.fetchSpendingGuard.mockResolvedValue(LIFTED);
    render(<SpendingGuardCard userId="u1" nonce={0} />);

    fireEvent.click(await screen.findByRole("button", { name: /Set aside \$85/ }));

    await waitFor(() => expect(api.allocateForCrunch).toHaveBeenCalledWith("u1", "cat1", "2099-11-02", 85));
    expect(await screen.findByText(/\$85\.00 set aside/)).toBeTruthy();
  });

  it("waves it off for the week", async () => {
    api.fetchSpendingGuard.mockResolvedValue(LIFTED);
    render(<SpendingGuardCard userId="u1" nonce={0} />);

    fireEvent.click(await screen.findByRole("button", { name: "Not this time" }));

    await waitFor(() => expect(api.dismissCrunchSuggestion).toHaveBeenCalledWith("u1", "cat1", "2099-11-02"));
  });

  it("shows the report card even with no crunch week ahead", async () => {
    api.fetchSpendingGuard.mockResolvedValue({ ...GUARD, upcoming: null, report_week: "2099-10-26",
      report: [{ category: "Delivery", set_aside: 60, spent: 52 }] });
    render(<SpendingGuardCard userId="u1" nonce={0} />);

    expect(await screen.findByText(/\$52\.00 of \$60\.00 on Delivery, inside what you set aside/)).toBeTruthy();
  });
});
