// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const fetchForecast = vi.fn();
vi.mock("../api", () => ({ fetchForecast: (...a: unknown[]) => fetchForecast(...a) }));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import CashFlowForecast from "./CashFlowForecast";
import { CashFlowForecast as Forecast } from "../types";

const day = (value: string) =>
  new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function forecast(overrides: Partial<Forecast> = {}): Forecast {
  return {
    starts_on: "2026-10-14",
    ends_on: "2026-12-31",
    ends_at_term_end: true,
    starting_balance: 1200,
    daily_spending: 20,
    spending_history_days: 56,
    points: [
      { on_date: "2026-10-14", balance: 1200 },
      { on_date: "2026-10-15", balance: 1180 },
      { on_date: "2026-10-16", balance: 1160 },
    ],
    events: [],
    negative_on: null,
    lowest_balance: 212.4,
    lowest_on: "2026-11-28",
    ending_balance: 300,
    runway: { liquid: 4500, daily_burn: 11.43, lasts_until: "2027-11-11" },
    run_rates: [],
    assumptions: ["Standing instructions run as scheduled.", "Tuition instalments aren't included."],
    ...overrides,
  };
}

async function show(f: Forecast | Error) {
  if (f instanceof Error) fetchForecast.mockRejectedValue(f);
  else fetchForecast.mockResolvedValue(f);
  const view = render(<CashFlowForecast nonce={0} />);
  await waitFor(() => expect(fetchForecast).toHaveBeenCalledWith("u1"));
  return view;
}

beforeEach(() => {
  fetchForecast.mockReset();
});
afterEach(cleanup);

describe("CashFlowForecast", () => {
  it("names the first day below zero, and how far off it is", async () => {
    const { container } = await show(forecast({ negative_on: "2026-12-16" }));
    expect(await screen.findByText(/go below \$0 on/)).toBeTruthy();
    expect(screen.getByText(day("2026-12-16"))).toBeTruthy();
    expect(container.textContent).toContain("(in 9 weeks)");
    expect(container.querySelector(".forecastBlockOver")).not.toBeNull();
    expect(container.querySelector(".forecastCross")).toBeNull(); // not a drawn point here
  });

  it("otherwise says it stays above zero, and where it is lowest", async () => {
    const { container } = await show(forecast());
    expect(await screen.findByText(/stay above \$0/)).toBeTruthy();
    expect(container.textContent).toContain("$212.40");
    expect(container.textContent).toContain(day("2026-11-28"));
    expect(container.querySelector(".forecastBlockOver")).toBeNull();
  });

  it("gives runway as a date, or says money in kept up", async () => {
    const { container, unmount } = await show(forecast());
    await screen.findByText(/Runway/);
    expect(container.textContent).toContain(day("2027-11-11"));
    unmount();

    const flat = await show(forecast({ runway: { liquid: 900, daily_burn: 0, lasts_until: null } }));
    expect(await screen.findByText("Over the last 56 days, money in has kept up with money out.")).toBeTruthy();
    flat.unmount();
  });

  it("lists the top three one-off places, at their pace", async () => {
    await show(forecast({
      run_rates: ["DoorDash", "Blenz", "Subway", "Tim Hortons"].map((merchant, i) => ({
        merchant, spent: 100 - i, occurrences: 3, projected: 200 - i * 10,
      })),
    }));
    expect(await screen.findByText("DoorDash")).toBeTruthy();
    expect(screen.getByText("Subway")).toBeTruthy();
    expect(screen.queryByText("Tim Hortons")).toBeNull();
    expect(screen.getByText("$200.00")).toBeTruthy();
  });

  it("always carries its assumptions", async () => {
    await show(forecast());
    expect(await screen.findByText("How this is worked out")).toBeTruthy();
    expect(screen.getByText("Tuition instalments aren't included.")).toBeTruthy();
  });

  it("marks the crossing on the curve when the day is in range", async () => {
    const { container } = await show(forecast({ negative_on: "2026-10-16" }));
    await screen.findByText(/go below/);
    expect(container.querySelector(".forecastCross")).not.toBeNull();
    expect(container.querySelector(".forecastZero")).toBeNull(); // the curve never dips below 0
  });

  it("says nothing with no money, no history and nothing scheduled", async () => {
    const { container } = await show(forecast({
      starting_balance: 0, spending_history_days: 0, events: [], runway: null,
    }));
    await Promise.resolve();
    expect(container.innerHTML).toBe("");
  });

  it("says nothing if the forecast fails", async () => {
    const { container } = await show(new Error("500"));
    await Promise.resolve();
    expect(container.innerHTML).toBe("");
  });
});
