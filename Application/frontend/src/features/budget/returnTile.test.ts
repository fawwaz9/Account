import { describe, expect, it } from "vitest";
import { returnTile } from "./returnTile";
import { AccountActivity, InvestmentReturn } from "./types";

/**
 * The tile that replaces Movements on an investment account.
 *
 * Its four states make four different claims, and the one that matters most is
 * the difference between "the holding did not move" and "nobody recorded what it
 * did". Collapsing those two is how a feature like this starts lying.
 */

function reading(over: Partial<InvestmentReturn> = {}): InvestmentReturn {
  return {
    difference_amount: 500,
    return_percent: 5,
    as_of: "2026-03-01",
    is_carried_forward: false,
    ledger_balance: 10_000,
    market_value: 10_500,
    month_gain: null,
    ...over,
  };
}

function activity(figure: InvestmentReturn | null): AccountActivity {
  return {
    account_id: "a1",
    account_name: "Investments",
    month: "2026-03-01",
    kind: "investment",
    balance: 10_000,
    total_in: 0,
    total_out: 0,
    net: 0,
    transaction_count: 4,
    planned: 0,
    remaining: 0,
    used_percent: 0,
    planned_is_derived: false,
    daily: [],
    by_category: [],
    balance_history: [],
    investment_return: figure,
    ledger_balance_at_month: 10_000,
  };
}

describe("returnTile", () => {
  it("reports the month's movement when the month has a reading and one before it", () => {
    const tile = returnTile(activity(reading({ month_gain: 125 })), "March 2026");

    expect(tile.label).toBe("Return · March 2026");
    expect(tile.value).toBe("+$125.00");
    expect(tile.tone).toBe("in");
  });

  it("reports a month that lost value as a loss", () => {
    // The case a returns feature always gets wrong by only ever rendering a plus.
    const tile = returnTile(activity(reading({ month_gain: -350 })), "March 2026");

    expect(tile.value).toBe("−$350.00");
    expect(tile.tone).toBe("out");
  });

  it("says nothing is recorded rather than showing a zero", () => {
    // "$0.00" would claim the holding was flat. Nobody said that.
    const tile = returnTile(activity(null), "March 2026");

    expect(tile.value).toBe("Not recorded");
    expect(tile.tone).toBeUndefined();
  });

  it("dates a carried-forward figure instead of attributing it to this month", () => {
    const tile = returnTile(
      activity(reading({ is_carried_forward: true, as_of: "2026-03-01" })),
      "May 2026",
    );

    expect(tile.label).toContain("March 2026");
    expect(tile.label).not.toContain("May 2026");
    expect(tile.value).toBe("+$500.00");
  });

  it("labels a first-ever reading as all-time, not as the month's movement", () => {
    // It has a level but nothing to subtract from. Calling it March's movement
    // would report the entire gain to date as having happened in one month.
    const tile = returnTile(activity(reading({ month_gain: null })), "March 2026");

    expect(tile.label).toBe("Return · all time");
    expect(tile.value).toBe("+$500.00");
  });

  it("prefers the month's movement over the level when both are available", () => {
    // The level is +$500 and the month moved +$125. The tile is the month's.
    const tile = returnTile(
      activity(reading({ difference_amount: 500, month_gain: 125 })),
      "March 2026",
    );

    expect(tile.value).toBe("+$125.00");
  });

  it("treats a zero movement as a real figure, unlike a missing one", () => {
    // A recorded month that genuinely did not move says so, and must not be
    // confused with the "Not recorded" case above.
    const tile = returnTile(activity(reading({ month_gain: 0 })), "March 2026");

    expect(tile.value).toBe("+$0.00");
    expect(tile.value).not.toBe("Not recorded");
  });
});
