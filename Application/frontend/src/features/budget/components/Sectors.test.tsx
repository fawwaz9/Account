// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Sectors from "./Sectors";
import { Account } from "../types";

/**
 * The return figure beside an account's balance.
 *
 * What is pinned here is not the layout but two rules the figure has to obey:
 * the sign is carried in the **text** and not only in a colour, and the figure
 * never appears on an account that has no reading to show. Audit #60 is already
 * open against this card for conveying an overdraft by its minus sign alone, so
 * a second meaning carried by colour here would deepen that rather than leave it.
 */

function account(over: Partial<Account> = {}): Account {
  return {
    id: "acct-1",
    name: "Investments",
    kind: "investment",
    income_share: 20,
    archived: false,
    position: 0,
    counts_toward_net_worth: true,
    balance: 10_000,
    role_locked: false,
    investment_return: {
      difference_amount: 320,
      return_percent: 3.2,
      as_of: "2026-03-01",
      is_carried_forward: false,
      ledger_balance: 10_000,
      market_value: 10_320,
      month_gain: null,
    },
    ...over,
  };
}

function show(accounts: Account[]) {
  return render(
    <MemoryRouter>
      <Sectors accounts={accounts} onEdit={vi.fn()} onAdd={vi.fn()} />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("the return beside the balance", () => {
  it("shows a gain with the sign in the text", () => {
    show([account()]);

    expect(screen.getByText("(+3.2%)")).toBeTruthy();
  });

  it("shows a loss with a minus in the text, not only in a colour", () => {
    show([
      account({
        investment_return: {
          ...account().investment_return!,
          difference_amount: -810,
          return_percent: -8.1,
        },
      }),
    ]);

    // U+2212, the same character formatMoney uses, so the two agree on screen.
    expect(screen.getByText("(−8.1%)")).toBeTruthy();
  });

  it("says in words what the figure means, and when it was taken", () => {
    // "(+3.2%)" read aloud on its own is cryptic, and the card shows the latest
    // reading there is -- which may be months old with nothing saying so.
    show([account()]);

    expect(
      screen.getByText("up 3.2% on what you put in, as of March 2026"),
    ).toBeTruthy();
  });

  it("describes a loss as down rather than up", () => {
    show([
      account({
        investment_return: {
          ...account().investment_return!,
          difference_amount: -810,
          return_percent: -8.1,
        },
      }),
    ]);

    expect(screen.getByText(/^down 8\.1% on what you put in/)).toBeTruthy();
  });

  it("does not announce the figure twice", () => {
    // The visible percentage is aria-hidden so the words carry it once, rather
    // than a screen reader reading both the punctuation and the sentence.
    show([account()]);

    expect(screen.getByText("(+3.2%)").getAttribute("aria-hidden")).toBe("true");
  });

  it("shows nothing on an investment account with no reading", () => {
    show([account({ investment_return: null })]);

    expect(screen.queryByText(/%\)/)).toBeNull();
    expect(screen.queryByText(/on what you put in/)).toBeNull();
  });

  it("shows nothing on a spending account", () => {
    show([account({ kind: "spending", name: "Chequing", investment_return: null })]);

    expect(screen.queryByText(/on what you put in/)).toBeNull();
  });

  it("shows the balance with no percentage when there is nothing to divide by", () => {
    // Everything withdrawn after a reading: the dollar level still exists but the
    // percentage does not, and the card must not invent one.
    show([
      account({
        balance: 0,
        investment_return: { ...account().investment_return!, return_percent: null },
      }),
    ]);

    expect(screen.queryByText(/%\)/)).toBeNull();
    expect(screen.getByText("$0.00")).toBeTruthy();
  });

  it("still shows the balance and the kind alongside it", () => {
    // The figure is an addition to the card, not a replacement for anything.
    show([account()]);

    expect(screen.getByText("$10,000.00")).toBeTruthy();
    expect(screen.getByText("Investment")).toBeTruthy();
  });
});
