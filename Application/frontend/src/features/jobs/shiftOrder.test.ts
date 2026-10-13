import { describe, expect, it } from "vitest";
import { arrangeShifts, upcomingMinutesByJob } from "./shiftOrder";
import { ShiftOccurrence } from "./types";

/**
 * The shift list's order (the owner's ask, 2026-10-12): past shifts needing
 * confirming first, nearest to today first; then upcoming; then confirmed ones
 * from the last 20 days. Today is Monday 12 October 2026 throughout.
 */
const TODAY = "2026-10-12";

function shift(on_date: string, over: Partial<ShiftOccurrence> = {}): ShiftOccurrence {
  return {
    event_id: `e-${on_date}`, job_id: "j1", job_name: "Cafe", on_date, title: "Cafe",
    scheduled_start: "09:00:00", scheduled_end: "13:00:00", location: null,
    scheduled_minutes: 240, worked_start: null, worked_end: null, counted_minutes: 240,
    confirmed: false, repeats: true, assumed: false,
    tip_amount: 0, tip_is_cash: false, tip_in_ledger: false, rate_override: null, notes: null,
    ...over,
  };
}

const past = (d: string) => shift(d, { assumed: true });
const done = (d: string) => shift(d, { confirmed: true });
const dates = (list: ShiftOccurrence[]) => list.map((s) => s.on_date);

describe("the shift list's order", () => {
  it("puts past shifts needing confirming first, nearest to today first", () => {
    const list = arrangeShifts([past("2026-09-30"), shift("2026-10-14"), past("2026-10-10"), done("2026-10-08")], TODAY);
    expect(dates(list)).toEqual(["2026-10-10", "2026-09-30", "2026-10-14", "2026-10-08"]);
  });

  it("lists upcoming shifts soonest first, after the ones needing confirming", () => {
    const list = arrangeShifts([shift("2026-10-30"), shift("2026-10-13"), shift("2026-10-20")], TODAY);
    expect(dates(list)).toEqual(["2026-10-13", "2026-10-20", "2026-10-30"]);
  });

  it("puts confirmed shifts last, most recent first", () => {
    const list = arrangeShifts([done("2026-10-01"), done("2026-10-09"), shift("2026-10-15")], TODAY);
    expect(dates(list)).toEqual(["2026-10-15", "2026-10-09", "2026-10-01"]);
  });

  it("drops a confirmed shift more than 20 days old, and keeps one on the 20th day", () => {
    const list = arrangeShifts([done("2026-09-21"), done("2026-09-22")], TODAY);
    expect(dates(list)).toEqual(["2026-09-22"]);
  });

  it("keeps a past shift nobody confirmed, however old, until it is confirmed", () => {
    const list = arrangeShifts([past("2026-07-20")], TODAY);
    expect(dates(list)).toEqual(["2026-07-20"]);
  });

  it("orders two shifts on one day by their start", () => {
    const list = arrangeShifts([
      shift("2026-10-13", { event_id: "late", scheduled_start: "17:00:00" }),
      shift("2026-10-13", { event_id: "early", scheduled_start: "08:00:00" }),
    ], TODAY);
    expect(list.map((s) => s.event_id)).toEqual(["early", "late"]);
  });
});

describe("a job card's hours", () => {
  it("counts today to three weeks out, as its line says, and nothing behind", () => {
    const totals = upcomingMinutesByJob([
      done("2026-10-05"), past("2026-10-11"), shift("2026-10-12"), shift("2026-11-02"), shift("2026-11-03"),
    ], TODAY);
    expect(totals.get("j1")).toBe(480);
  });

  it("keeps jobs apart", () => {
    const totals = upcomingMinutesByJob([shift("2026-10-13"), shift("2026-10-14", { job_id: "j2", counted_minutes: 60 })], TODAY);
    expect(totals.get("j1")).toBe(240);
    expect(totals.get("j2")).toBe(60);
  });
});
