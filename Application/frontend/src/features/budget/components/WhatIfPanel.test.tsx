// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchWhatIf: vi.fn() };
vi.mock("../api", () => ({ fetchWhatIf: (...a: unknown[]) => api.fetchWhatIf(...a) }));

import WhatIfPanel from "./WhatIfPanel";
import { WhatIfIn, WhatIfResult } from "../types";

/** Phase 4 item 14: the year plan re-run with changes; money only, nothing saved. */

function outcome(ending: number) {
  return { ending_balance: ending, lowest_balance: 1500, lowest_on: "2026-11-11", negative_on: null,
    points: [{ on_date: "2026-10-31", balance: 1600 }, { on_date: "2027-04-30", balance: ending }] };
}

function result(body: WhatIfIn): WhatIfResult {
  const diff = -(body.monthly_spending_change ?? 0) * 6;
  return {
    starts_on: "2026-10-31", ends_on: "2027-04-30", baseline: outcome(5000), scenario: outcome(5000 + diff),
    difference: diff, exam_season: { starts_on: "2026-11-24", ends_on: "2026-12-14" },
    assumptions: ["Standing instructions run as scheduled."], capped: [],
  };
}

beforeEach(() => {
  api.fetchWhatIf.mockReset().mockImplementation((_u: string, body: WhatIfIn) => Promise.resolve(result(body)));
});
afterEach(cleanup);

describe("WhatIfPanel", () => {
  it("starts from the plan with nothing changed", async () => {
    render(<WhatIfPanel userId="u1" />);

    await waitFor(() => expect(api.fetchWhatIf).toHaveBeenCalled());
    expect(api.fetchWhatIf.mock.calls[0][1]).toEqual({
      hours_per_week: 0, hourly_rate: null, monthly_spending_change: 0,
      no_shifts_from: null, no_shifts_until: null, purchases: [],
    });
    expect(await screen.findByText(/No change by/)).toBeTruthy();
  });

  it("sends a change and says what it does by the plan's end", async () => {
    render(<WhatIfPanel userId="u1" />);
    await screen.findByText(/No change by/);

    fireEvent.change(screen.getByRole("spinbutton", { name: "Spending a month more or less" }), { target: { value: "-100" } });

    await waitFor(() => expect(api.fetchWhatIf.mock.lastCall?.[1].monthly_spending_change).toBe(-100));
    expect(await screen.findByText(/\+\$600\.00 by/)).toBeTruthy();
  });

  it("fills the exam-season stretch it was offered", async () => {
    render(<WhatIfPanel userId="u1" />);

    fireEvent.click(await screen.findByRole("button", { name: /Exam season/ }));

    await waitFor(() => expect(api.fetchWhatIf.mock.lastCall?.[1]).toMatchObject({
      no_shifts_from: "2026-11-24", no_shifts_until: "2026-12-14" }));
  });

  it("adds a purchase only once it has a name, an amount and a day, and takes it out again", async () => {
    render(<WhatIfPanel userId="u1" />);
    await screen.findByText(/No change by/);

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.queryByRole("button", { name: /Remove/ })).toBeNull();

    fireEvent.change(screen.getByRole("textbox", { name: "What it is" }), { target: { value: "laptop" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "How much" }), { target: { value: "800" } });
    fireEvent.change(screen.getByLabelText("When"), { target: { value: "2026-11-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(api.fetchWhatIf.mock.lastCall?.[1].purchases).toEqual(
      [{ label: "laptop", amount: 800, on_date: "2026-11-20" }]));
    fireEvent.click(screen.getByRole("button", { name: "Remove laptop" }));
    await waitFor(() => expect(api.fetchWhatIf.mock.lastCall?.[1].purchases).toEqual([]));
  });
});
