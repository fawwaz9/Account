// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import WhereItWent from "./WhereItWent";
import { CategorySpend } from "../types";

/**
 * A limit is the difference between a number and a judgement, so the rules
 * about when one is shown -- and when one is emphatically not -- are worth
 * pinning. The dangerous direction is showing a limit where it does not apply:
 * the account detail page reuses this section for a single account, and a
 * whole-budget limit judged against one account's share would look
 * authoritative while answering a question nobody asked.
 */

// Explicit, because testing-library only auto-cleans when vitest runs with
// `globals: true` and this project deliberately does not. Without it each
// render stacks on the last and "is there a progressbar?" -- the question half
// this file asks -- finds one belonging to a previous test.
afterEach(cleanup);

function entry(over: Partial<CategorySpend> = {}): CategorySpend {
  return {
    category_id: "c1",
    category_name: "Groceries",
    actual: 412,
    limit: 400,
    remaining: -12,
    used_percent: 103,
    limit_is_override: false,
    ...over,
  };
}

describe("a category with a limit", () => {
  it("draws a bar and says how far over it is", () => {
    render(<WhereItWent entries={[entry()]} />);

    expect(screen.getByRole("progressbar")).toBeDefined();
    expect(screen.getByText("$12.00 over")).toBeDefined();
  });

  it("says how much is left when under", () => {
    render(<WhereItWent entries={[entry({
      category_name: "Transport", actual: 88, limit: 150, remaining: 62, used_percent: 58.7,
    })]} />);

    expect(screen.getByText("$62.00 left")).toBeDefined();
  });

  /**
   * The server's figure, not a recomputed one. ProgressBar's own docstring
   * explains why: the two disagree at the `close` boundary, where 89.96 rounds
   * to 90.0 server-side and stays 0.8996 here, so one says "close" and the
   * other does not for the same money.
   */
  it("reports the server's percentage rather than deriving its own", () => {
    render(<WhereItWent entries={[entry({ actual: 100, limit: 400, used_percent: 90.0 })]} />);

    expect(screen.getByRole("progressbar").getAttribute("aria-valuetext"))
      .toBe("90.0% of target used");
  });

  it("marks a month that differs from the standing limit", () => {
    render(<WhereItWent entries={[entry({ limit_is_override: true })]} />);

    expect(screen.getByText(/this month only/)).toBeDefined();
  });
});

describe("a category with no limit", () => {
  /**
   * The load-bearing negative. This is every row on the account detail page and
   * every category nobody has budgeted, and all of them must render exactly as
   * they did before limits existed.
   */
  it("draws no bar at all", () => {
    render(<WhereItWent entries={[entry({ limit: null, remaining: 0, used_percent: 0 })]} />);

    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText("$412.00")).toBeDefined();
  });

  it("is not editable when the page offers no handler", () => {
    render(<WhereItWent entries={[entry({ limit: null })]} />);

    expect(screen.queryByRole("button", { name: /Set a limit/ })).toBeNull();
  });
});

describe("editing this month's limit", () => {
  it("sends the number typed", async () => {
    const onSetLimit = vi.fn(async () => undefined);
    render(<WhereItWent entries={[entry()]} onSetLimit={onSetLimit} />);

    fireEvent.click(screen.getByRole("button", { name: /Change this month's limit for Groceries/ }));
    fireEvent.change(screen.getByLabelText("Limit for Groceries this month"), {
      target: { value: "500" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onSetLimit).toHaveBeenCalledWith("c1", 500));
  });

  /**
   * Blank clears the override rather than setting a limit of nothing. Sending 0
   * here would close the month to all spending -- a real instruction, but not
   * the one an emptied box means.
   */
  it("clears the override when the box is emptied, rather than setting zero", async () => {
    const onSetLimit = vi.fn(async () => undefined);
    render(<WhereItWent entries={[entry()]} onSetLimit={onSetLimit} />);

    fireEvent.click(screen.getByRole("button", { name: /Change this month's limit for Groceries/ }));
    fireEvent.change(screen.getByLabelText("Limit for Groceries this month"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onSetLimit).toHaveBeenCalledWith("c1", null));
  });

  /**
   * Uncategorised has no row to hang a limit on, so it must not offer to set
   * one -- and, the part that actually broke, must not open an editor by itself.
   *
   * Its `category_id` is null and `editing` also starts as null, so the
   * "is this row being edited?" test was true on first render and the row came
   * up as a live input with a Save button, unprompted. The earlier version of
   * this test looked only for a button named like a limit, and the editor's
   * button says "Save" -- so it passed while the bug was on screen. It asserts
   * what the row *shows* now, not merely what it lacks.
   */
  it("shows Uncategorised as a plain figure, with no editor and no control", () => {
    const onSetLimit = vi.fn(async () => undefined);
    render(
      <WhereItWent
        entries={[entry({
          category_id: null, category_name: "Uncategorised", actual: 23,
          limit: null, remaining: 0, used_percent: 0,
        })]}
        onSetLimit={onSetLimit}
      />,
    );

    expect(screen.getByText("$23.00")).toBeDefined();
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("button", { name: /limit/i })).toBeNull();
  });
});
