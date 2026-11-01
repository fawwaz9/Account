// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const put = vi.fn();
vi.mock("../../services/apiClient", () => ({ put: (...a: unknown[]) => put(...a) }));
const refreshUser = vi.fn();
vi.mock("../../app/auth/AuthContext", () => ({ useAuth: () => ({ refreshUser }) }));

import BriefingSetting, { hourLabel } from "./BriefingSetting";

/** Phase 4 item 6: the daily briefing push, off until an hour is chosen. */

beforeEach(() => { put.mockReset().mockResolvedValue({ hour: 7 }); refreshUser.mockReset().mockResolvedValue(undefined); });
afterEach(cleanup);

describe("BriefingSetting", () => {
  it("is off until chosen, then saves the hour through its own route", async () => {
    render(<BriefingSetting userId="u1" hour={null} />);
    const select = screen.getByRole("combobox", { name: "When the daily briefing goes out" }) as HTMLSelectElement;
    expect(select.value).toBe("off");

    fireEvent.change(select, { target: { value: "7" } });

    await waitFor(() => expect(put).toHaveBeenCalledWith("briefing/u1/schedule", { hour: 7 }));
    expect(await screen.findByText(/Every day at 7am/)).toBeTruthy();
  });

  it("turns off with null", async () => {
    render(<BriefingSetting userId="u1" hour={8} />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "off" } });

    await waitFor(() => expect(put).toHaveBeenCalledWith("briefing/u1/schedule", { hour: null }));
  });

  it("goes back to what it was when saving fails", async () => {
    put.mockRejectedValue(new Error("down"));
    render(<BriefingSetting userId="u1" hour={8} />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "6" } });

    expect(await screen.findByText(/Couldn't save/)).toBeTruthy();
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("8");
  });

  it("reads hours as a clock does", () => {
    expect([hourLabel(0), hourLabel(7), hourLabel(12), hourLabel(17)]).toEqual(["12am", "7am", "12pm", "5pm"]);
  });
});
