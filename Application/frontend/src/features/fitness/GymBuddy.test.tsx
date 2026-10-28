// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = { fetchGymBuddies: vi.fn(), saveGymBuddy: vi.fn() };
vi.mock("./api", () => ({
  fetchGymBuddies: (...a: unknown[]) => api.fetchGymBuddies(...a),
  saveGymBuddy: (...a: unknown[]) => api.saveGymBuddy(...a),
}));

import GymBuddy from "./GymBuddy";

/** Phase 3 item 13: gym buddies among partners and teammates only. */

const quiet = { looking: false, times: null, note: null, buddies: [] };
const found = {
  looking: true, times: "mornings", note: null,
  buddies: [{ name: "Alex", times: "weekday evenings", note: "beginner", via: "partner, Ultimate" }],
};

beforeEach(() => { Object.values(api).forEach((fn) => fn.mockReset()); });
afterEach(cleanup);

describe("GymBuddy", () => {
  it("starts looking with when you could go, then lists connections looking too", async () => {
    api.fetchGymBuddies.mockResolvedValue(quiet);
    api.saveGymBuddy.mockResolvedValue(found);
    render(<GymBuddy userId="u1" />);
    fireEvent.change(await screen.findByLabelText("When you could go"), { target: { value: " mornings " } });
    fireEvent.click(screen.getByRole("button", { name: "I'm looking" }));
    await waitFor(() => expect(api.saveGymBuddy).toHaveBeenCalledWith("u1", true, "mornings", null));
    const list = await screen.findByRole("list", { name: "Also looking" });
    expect(within(list).getByRole("listitem").textContent).toBe(
      "Alex · partner, Ultimate · weekday evenings · beginner");
  });

  it("stops looking", async () => {
    api.fetchGymBuddies.mockResolvedValue(found);
    api.saveGymBuddy.mockResolvedValue(quiet);
    render(<GymBuddy userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Stop looking" }));
    await waitFor(() => expect(api.saveGymBuddy).toHaveBeenCalledWith("u1", false, "mornings", null));
    expect(await screen.findByRole("button", { name: "I'm looking" })).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Also looking" })).toBeNull();
  });

  it("says when no connection is looking", async () => {
    api.fetchGymBuddies.mockResolvedValue({ ...found, buddies: [] });
    render(<GymBuddy userId="u1" />);
    expect(await screen.findByText(/None of your partners or teammates is looking/)).toBeTruthy();
  });

  it("renders nothing when the read fails", async () => {
    api.fetchGymBuddies.mockRejectedValue(new Error("down"));
    const { container } = render(<GymBuddy userId="u1" />);
    await waitFor(() => expect(api.fetchGymBuddies).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});
