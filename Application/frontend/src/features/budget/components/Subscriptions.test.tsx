// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchSubscriptions: vi.fn(), confirmSubscription: vi.fn() };
vi.mock("../api", () => ({
  fetchSubscriptions: (...a: unknown[]) => api.fetchSubscriptions(...a),
  confirmSubscription: (...a: unknown[]) => api.confirmSubscription(...a),
}));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import Subscriptions from "./Subscriptions";

const candidate = {
  description: "NETFLIX.COM", account_id: "a1", category_id: null, cadence: "monthly",
  median_amount: 16.49, first_seen: "2026-07-03", last_seen: "2026-09-03",
  next_expected_on: "2026-10-03",
  occurrences: [{ transaction_id: "t1", on_date: "2026-07-03", amount: 16.49 }],
  suggested: { kind: "expense", amount: 16.49, description: "Netflix.com", account_id: "a1",
    to_account_id: null, category_id: null, starts_on: "2026-10-03",
    recurrence: { freq: "monthly", interval: 1, byday: [], until: null, count: null }, active: true },
};

beforeEach(() => {
  api.fetchSubscriptions.mockReset();
  api.confirmSubscription.mockReset();
  api.fetchSubscriptions.mockResolvedValue([candidate]);
  api.confirmSubscription.mockResolvedValue({});
});
afterEach(cleanup);

describe("Subscriptions' until when", () => {
  it("says ongoing until a date is chosen, and sends none", async () => {
    render(<Subscriptions nonce={0} onConfirmed={vi.fn()} />);
    expect(await screen.findByText("ongoing")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Make it a standing instruction" }));
    await waitFor(() => expect(api.confirmSubscription).toHaveBeenCalledWith("u1", candidate, null));
  });

  it("sends the last date when one is chosen", async () => {
    const onConfirmed = vi.fn();
    render(<Subscriptions nonce={0} onConfirmed={onConfirmed} />);
    const input = (await screen.findByLabelText("NETFLIX.COM runs until")) as HTMLInputElement;
    expect(input.min).toBe("2026-10-03");
    fireEvent.change(input, { target: { value: "2027-04-30" } });
    expect(screen.queryByText("ongoing")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Make it a standing instruction" }));
    await waitFor(() => expect(api.confirmSubscription).toHaveBeenCalledWith("u1", candidate, "2027-04-30"));
    await waitFor(() => expect(onConfirmed).toHaveBeenCalled());
  });

  it("shows why a date was refused", async () => {
    api.confirmSubscription.mockRejectedValue(new Error("The rule ends before it starts"));
    render(<Subscriptions nonce={0} onConfirmed={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Make it a standing instruction" }));
    expect(await screen.findByText("The rule ends before it starts")).toBeTruthy();
  });
});
