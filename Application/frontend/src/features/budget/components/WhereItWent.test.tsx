// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import WhereItWent from "./WhereItWent";
import { CategorySpend } from "../types";

/**
 * A limit belongs to one account, so the dangerous direction is showing one
 * where it does not apply. The budget page spans every account; a limit shown
 * there would be judged against a fraction of the spending and look
 * authoritative doing it, which is what got the first attempt at this removed.
 */

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
  it("draws a bar and says how far over", () => {
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
   * The server's figure, not a recomputed one -- ProgressBar's own docstring
   * explains that the two disagree at the `close` boundary, where 89.96 rounds
   * to 90.0 server-side and stays 0.8996 here.
   */
  it("reports the server's percentage rather than deriving its own", () => {
    render(<WhereItWent entries={[entry({ actual: 100, limit: 400, used_percent: 90.0 })]} />);

    expect(screen.getByRole("progressbar").getAttribute("aria-valuetext"))
      .toBe("90.0% of target used");
  });
});

describe("a category with no limit", () => {
  /**
   * Every row on the budget page, and every category nobody has budgeted on
   * this account. All of them must render as they did before limits existed.
   */
  it("draws no bar at all", () => {
    render(<WhereItWent entries={[entry({ limit: null, remaining: 0, used_percent: 0 })]} />);

    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText("$412.00")).toBeDefined();
  });

  it("offers no control when the page passes no handler", () => {
    render(<WhereItWent entries={[entry({ limit: null })]} />);
    expect(screen.queryByRole("button", { name: /limit/i })).toBeNull();
  });
});

describe("editing this account's limit", () => {
  it("sets the standing limit by default", async () => {
    const onSetLimit = vi.fn(async () => undefined);
    render(<WhereItWent entries={[entry()]} onSetLimit={onSetLimit} />);

    fireEvent.click(screen.getByRole("button", { name: /Change the limit for Groceries/ }));
    fireEvent.change(screen.getByLabelText("Limit for Groceries on this account"), {
      target: { value: "500" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    // false -- the standing figure, which carries into every month.
    await waitFor(() => expect(onSetLimit).toHaveBeenCalledWith("c1", 500, false));
  });

  it("sets only this month when asked to", async () => {
    const onSetLimit = vi.fn(async () => undefined);
    render(<WhereItWent entries={[entry()]} onSetLimit={onSetLimit} />);

    fireEvent.click(screen.getByRole("button", { name: /Change the limit for Groceries/ }));
    fireEvent.change(screen.getByLabelText("Limit for Groceries on this account"), {
      target: { value: "600" },
    });
    fireEvent.click(screen.getByLabelText("This month only"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onSetLimit).toHaveBeenCalledWith("c1", 600, true));
  });

  /**
   * Opening an already-overridden row must not silently rewrite the standing
   * figure behind it. The box starts ticked because that is what the row shows.
   */
  it("opens on this month when the row is already an override", async () => {
    const onSetLimit = vi.fn(async () => undefined);
    render(<WhereItWent entries={[entry({ limit_is_override: true })]} onSetLimit={onSetLimit} />);

    fireEvent.click(screen.getByRole("button", { name: /Change the limit for Groceries/ }));
    expect((screen.getByLabelText("This month only") as HTMLInputElement).checked).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    // 400, the limit the row is showing -- not 412, which is what was spent.
    await waitFor(() => expect(onSetLimit).toHaveBeenCalledWith("c1", 400, true));
  });

  it("says when a row is showing an overridden month", () => {
    render(<WhereItWent entries={[entry({ limit_is_override: true })]} />);
    expect(screen.getByText(/this month only/)).toBeDefined();
  });

  /**
   * Blank removes the limit rather than setting one of nothing. Sending 0 would
   * close the category to all spending -- a real instruction, but not the one
   * an emptied box means, and it would also keep the account's target derived.
   */
  it("clears the limit when emptied, rather than setting zero", async () => {
    const onSetLimit = vi.fn(async () => undefined);
    render(<WhereItWent entries={[entry()]} onSetLimit={onSetLimit} />);

    fireEvent.click(screen.getByRole("button", { name: /Change the limit for Groceries/ }));
    fireEvent.change(screen.getByLabelText("Limit for Groceries on this account"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onSetLimit).toHaveBeenCalledWith("c1", null, false));
  });

  /**
   * Uncategorised has no row to hang a limit on -- and, the part that actually
   * broke once, must not open an editor by itself. Its id is null and `editing`
   * also starts null, so the "is this row being edited?" test was true on first
   * render. The earlier version of this test looked only for a button named
   * like a limit, and the editor's button says "Save", so it passed while the
   * bug was on screen. It asserts what the row *shows* now.
   */
  it("shows Uncategorised as a plain figure, with no editor", () => {
    render(
      <WhereItWent
        entries={[entry({
          category_id: null, category_name: "Uncategorised", actual: 23,
          limit: null, remaining: 0, used_percent: 0,
        })]}
        onSetLimit={vi.fn(async () => undefined)}
      />,
    );

    expect(screen.getByText("$23.00")).toBeDefined();
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});
