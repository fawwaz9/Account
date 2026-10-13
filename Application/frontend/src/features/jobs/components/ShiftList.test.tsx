// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ShiftList, { heldTip } from "./ShiftList";
import { ShiftOccurrence } from "../types";

/**
 * The red "!" on a confirmed shift whose cash tip is waiting for an account.
 *
 * The API has sent tip_in_ledger for a while and nothing showed it, so a tip
 * with nowhere to go was invisible. Now that no account chosen means held, it
 * must be seen -- and only where it is true.
 */
function occurrence(over: Partial<ShiftOccurrence> = {}): ShiftOccurrence {
  return {
    event_id: "e1", job_id: "j1", job_name: "Cafe", on_date: "2026-10-05", title: "Cafe",
    scheduled_start: "09:00:00", scheduled_end: "13:00:00", location: null,
    scheduled_minutes: 240, worked_start: null, worked_end: null, counted_minutes: 240,
    confirmed: true, repeats: false, assumed: false,
    tip_amount: 40, tip_is_cash: true, tip_in_ledger: false,
    rate_override: null, notes: null,
    ...over,
  };
}

function show(shift: ShiftOccurrence) {
  return render(
    <MemoryRouter>
      <ShiftList shifts={[shift]} onConfirm={() => {}} onRemove={() => {}} busy={false} />
    </MemoryRouter>,
  );
}

// Pinned: the list drops confirmed shifts after 20 days, so against the real
// clock these fixtures would start vanishing on their own.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-12T18:00:00Z"));
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("a held cash tip", () => {
  it("shows a red ! on a confirmed shift whose cash tip is not in the budget", () => {
    show(occurrence());
    const mark = screen.getByRole("button", { name: "This tip is not in your budget" });
    expect(mark.textContent).toBe("!");
  });

  it("links to the Financial tab of Settings when opened", () => {
    show(occurrence());
    fireEvent.click(screen.getByRole("button", { name: "This tip is not in your budget" }));

    const link = screen.getByRole("link", { name: "Choose in Settings" });
    expect(link.getAttribute("href")).toBe("/settings?tab=financial");
  });

  it.each([
    ["in the budget already", { tip_in_ledger: true }],
    ["paid on the cheque", { tip_is_cash: false }],
    ["no tip at all", { tip_amount: 0 }],
    ["not confirmed yet", { confirmed: false }],
  ])("shows nothing when the tip is %s", (_label, over) => {
    show(occurrence(over));
    expect(screen.queryByRole("button", { name: "This tip is not in your budget" })).toBeNull();
    expect(heldTip(occurrence(over))).toBe(false);
  });
});

describe("the order on the page", () => {
  it("is the arranged order: needing confirming, then upcoming, then confirmed", () => {
    const list = [
      occurrence({ event_id: "done", on_date: "2026-10-08", confirmed: true, tip_amount: 0 }),
      occurrence({ event_id: "soon", on_date: "2026-10-14", confirmed: false, tip_amount: 0 }),
      occurrence({ event_id: "late", on_date: "2026-10-09", confirmed: false, assumed: true, tip_amount: 0 }),
      occurrence({ event_id: "old", on_date: "2026-09-01", confirmed: true, tip_amount: 0 }),
    ];
    const { container } = render(
      <MemoryRouter>
        <ShiftList shifts={list} onConfirm={() => {}} onRemove={() => {}} busy={false} />
      </MemoryRouter>,
    );
    const rows = [...container.querySelectorAll(".shiftWhen")].map((row) => row.textContent);
    expect(rows).toHaveLength(3);
    expect(container.querySelectorAll(".shiftRow")[0].classList.contains("shiftRowAssumed")).toBe(true);
    expect(container.querySelectorAll(".shiftRow")[2].querySelector(".shiftStateDone")).not.toBeNull();
  });
});
