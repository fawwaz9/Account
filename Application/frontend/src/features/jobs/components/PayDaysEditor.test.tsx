// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PayDaysEditor, { startingPayDays } from "./PayDaysEditor";
import { PayDays } from "../types";

/** The days-of-the-month editor on the job form (decided 2026-10-03). */

afterEach(cleanup);

const SEMI: PayDays = { dates: [15], last_day: true, nth_weekdays: [], weekend: "previous", until: null };

function show(value: PayDays) {
  const onChange = vi.fn();
  render(<PayDaysEditor value={value} onChange={onChange} />);
  return onChange;
}

describe("the pay days editor", () => {
  it("starts on the first pay date's day of the month, moving weekend dates to the Friday before", () => {
    expect(startingPayDays("2026-09-15")).toEqual(
      { dates: [15], last_day: false, nth_weekdays: [], weekend: "previous", until: null });
  });

  it("edits a date", () => {
    const onChange = show(SEMI);
    fireEvent.change(screen.getByLabelText("Pay date 1, day of the month"), { target: { value: "20" } });
    expect(onChange).toHaveBeenCalledWith({ ...SEMI, dates: [20] });
  });

  it("adds a second date", () => {
    const onChange = show(SEMI);
    fireEvent.click(screen.getByRole("button", { name: "Add a date" }));
    expect(onChange.mock.calls[0][0].dates).toHaveLength(2);
  });

  it("chooses where a weekend date goes", () => {
    const onChange = show(SEMI);
    fireEvent.change(screen.getByLabelText("If it lands on a weekend"), { target: { value: "next" } });
    expect(onChange).toHaveBeenCalledWith({ ...SEMI, weekend: "next" });
  });

  it("switches to a weekday of the month, which stands alone", () => {
    const onChange = show(SEMI);
    fireEvent.click(screen.getByRole("radio", { name: "A weekday in the month" }));
    const next = onChange.mock.calls[0][0] as PayDays;
    expect(next.dates).toEqual([]);
    expect(next.last_day).toBe(false);
    expect(next.nth_weekdays).toEqual([{ n: -1, day: "FR" }]);
  });

  it("edits which week and which day", () => {
    const value: PayDays = { ...SEMI, dates: [], last_day: false, nth_weekdays: [{ n: -1, day: "FR" }] };
    const onChange = show(value);
    fireEvent.change(screen.getByLabelText("Which week, pay day 1"), { target: { value: "2" } });
    expect(onChange).toHaveBeenLastCalledWith({ ...value, nth_weekdays: [{ n: 2, day: "FR" }] });
    fireEvent.change(screen.getByLabelText("Which day, pay day 1"), { target: { value: "TH" } });
    expect(onChange).toHaveBeenLastCalledWith({ ...value, nth_weekdays: [{ n: -1, day: "TH" }] });
  });

  it("never lets the last pay day go: the last day cannot be unticked with no dates left", () => {
    show({ ...SEMI, dates: [] });
    expect((screen.getByRole("checkbox", { name: "The last day of the month" }) as HTMLInputElement).disabled).toBe(true);
  });

  it("only offers to remove a date while another pay day remains", () => {
    show({ ...SEMI, last_day: false });
    expect(screen.queryByRole("button", { name: "Remove pay date 1" })).toBeNull();
  });
});
