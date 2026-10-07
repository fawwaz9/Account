// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const api = { fetchShiftConflicts: vi.fn(), fetchTaxPacket: vi.fn() };
vi.mock("../api", () => ({
  fetchShiftConflicts: (...a: unknown[]) => api.fetchShiftConflicts(...a),
  fetchTaxPacket: (...a: unknown[]) => api.fetchTaxPacket(...a),
}));

import ShiftConflictsPanel from "./ShiftConflictsPanel";
import TaxPacketPanel, { defaultYear } from "./TaxPacketPanel";
import { ShiftConflict } from "../types";

/** Phase 2 item 14: shifts near exams, and the tax packet. */

const base: ShiftConflict = {
  kind: "crowds", shift_event_id: "s1", shift_on: "2026-12-13", shift_start: "17:00:00", shift_end: "23:00:00",
  job_id: "j1", job_name: "Cafe", exam_event_id: "e1", exam_title: "Final", exam_kind: "final",
  exam_on: "2026-12-14", exam_start: "08:30:00", course_code: "CPSC 221", hours_between: 9.5,
};

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

describe("ShiftConflictsPanel", () => {
  it("says which shift crowds which exam, and by how much", async () => {
    api.fetchShiftConflicts.mockResolvedValue({ buffer_hours: 12, conflicts: [
      base, { ...base, kind: "overlap", shift_event_id: "s2", hours_between: 0, exam_start: null },
    ] });
    render(<ShiftConflictsPanel userId="u1" nonce={0} />);
    expect(await screen.findByText(/Cafe, .* ends 9.5h before CPSC 221 Final/)).toBeTruthy();
    expect(screen.getByText(/runs into CPSC 221 Final .*time not set/)).toBeTruthy();
    expect(screen.getByText(/less than 12h before an exam/)).toBeTruthy();
  });

  it("says nothing when there is nothing to flag, or the read fails", async () => {
    api.fetchShiftConflicts.mockResolvedValue({ buffer_hours: 12, conflicts: [] });
    const { container } = render(<ShiftConflictsPanel userId="u1" nonce={0} />);
    await waitFor(() => expect(api.fetchShiftConflicts).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});

describe("TaxPacketPanel", () => {
  it("before May defaults to last year, from May this year", () => {
    expect(defaultYear("2027-03-10")).toBe(2026);
    expect(defaultYear("2026-10-07")).toBe(2026);
  });

  it("lays out the year from what was recorded, and says it is not tax advice", async () => {
    api.fetchTaxPacket.mockResolvedValue({
      year: 2026, gross: 3500, income_tax: 440, cpp: 50, ei: 16, other_deductions: 10, net: 2984,
      cash_tips: 30, tuition_paid: 3200,
      employers: [{ job_name: "Cafe", employer: "Cafe Ltd", paycheques: 2, gross: 1500, net: 1284,
                    cash_tips: 30, other_tips: 0,
                    deductions: [{ kind: "income_tax", label: "Income tax", amount: 140 },
                                 { kind: "other", label: "Union dues", amount: 10 }] }],
    });
    render(<TaxPacketPanel userId="u1" nonce={0} />);
    expect(await screen.findByText("Cafe · Cafe Ltd")).toBeTruthy();
    expect(screen.getByText("Union dues")).toBeTruthy();
    expect(screen.getByText("Tuition paid")).toBeTruthy();
    expect(screen.getByText(/Check it against your T4s/)).toBeTruthy();
    expect(screen.getByText(/not tax advice/)).toBeTruthy();
  });

  it("says when a year has nothing recorded", async () => {
    api.fetchTaxPacket.mockResolvedValue({
      year: 2026, gross: 0, income_tax: 0, cpp: 0, ei: 0, other_deductions: 0, net: 0, cash_tips: 0,
      tuition_paid: 0, employers: [],
    });
    render(<TaxPacketPanel userId="u1" nonce={0} />);
    expect(await screen.findByText(/No paycheques or tuition recorded for 2026/)).toBeTruthy();
  });
});
