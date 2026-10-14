// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

/** Making, editing and deleting a season (D7). */

const api = vi.hoisted(() => ({ createSeason: vi.fn(), updateSeason: vi.fn(), deleteSeason: vi.fn() }));
vi.mock("./api", () => api);
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import SeasonsModal from "./SeasonsModal";

afterEach(() => { cleanup(); vi.clearAllMocks(); });

const FALL = { id: "fall", name: "Fall 2026 co-op", starts: "2026-09", ends: "2026-12" };

function show(seasons = [FALL]) {
  const onSaved = vi.fn();
  render(<SeasonsModal open seasons={seasons} onClose={() => {}} onSaved={onSaved} />);
  return onSaved;
}

function fill(name: string, starts: string, ends: string) {
  fireEvent.change(screen.getByLabelText(/season/i, { selector: "input" }), { target: { value: name } });
  fireEvent.change(screen.getByLabelText("From"), { target: { value: starts } });
  fireEvent.change(screen.getByLabelText("To"), { target: { value: ends } });
}

describe("the seasons dialog", () => {
  it("adds a season with its months, and hands it back to be shown", async () => {
    const made = { id: "s2", name: "Summer 2027", starts: "2027-01", ends: "2027-04" };
    api.createSeason.mockResolvedValue(made);
    const onSaved = show([]);
    fill("Summer 2027", "2027-01", "2027-04");
    fireEvent.click(screen.getByRole("button", { name: "Add season" }));
    await waitFor(() => expect(api.createSeason).toHaveBeenCalledWith("u1",
      { name: "Summer 2027", starts: "2027-01", ends: "2027-04" }));
    expect(onSaved).toHaveBeenCalledWith(made);
  });

  it("refuses a season that ends before it starts, before asking the server", () => {
    show([]);
    fill("Backwards", "2027-04", "2027-01");
    fireEvent.click(screen.getByRole("button", { name: "Add season" }));
    expect(api.createSeason).not.toHaveBeenCalled();
    expect(screen.getByText("A season ends on or after the month it starts.")).toBeTruthy();
  });

  it("edits a season in place", async () => {
    api.updateSeason.mockResolvedValue({ ...FALL, ends: "2027-01" });
    show();
    fireEvent.click(screen.getByRole("button", { name: "Edit Fall 2026 co-op" }));
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2027-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save season" }));
    await waitFor(() => expect(api.updateSeason).toHaveBeenCalledWith("u1", "fall",
      { name: "Fall 2026 co-op", starts: "2026-09", ends: "2027-01" }));
  });

  it("deletes only after asking, and says no application goes with it", async () => {
    api.deleteSeason.mockResolvedValue({ deleted: true });
    show();
    fireEvent.click(screen.getByRole("button", { name: "Delete Fall 2026 co-op" }));
    expect(api.deleteSeason).not.toHaveBeenCalled();
    expect(screen.getByText(/No application is deleted with it/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Delete the season" }));
    await waitFor(() => expect(api.deleteSeason).toHaveBeenCalledWith("u1", "fall"));
  });
});
