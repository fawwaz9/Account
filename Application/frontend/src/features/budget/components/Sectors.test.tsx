// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Sectors, { positionChanges } from "./Sectors";
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

  it("still shows the gain when there is no percentage to divide out", () => {
    // Nothing paid in, but a recorded gain. The percentage is genuinely
    // uncomputable, and an earlier version of this card gated the WHOLE figure on
    // the percentage -- so an account up $320 showed nothing at all. The headline
    // carries it now and the percentage is simply absent.
    show([
      account({
        balance: 0,
        investment_return: { ...account().investment_return!, return_percent: null },
      }),
    ]);

    expect(screen.queryByText(/%\)/)).toBeNull();
    expect(screen.getByText("$320.00")).toBeTruthy();
    expect(screen.getByText("$0.00 paid in")).toBeTruthy();
  });

  it("still shows the kind alongside the figure", () => {
    show([account()]);

    expect(screen.getByText("Investment")).toBeTruthy();
  });
});

describe("the headline figure", () => {
  it("is what the holding is worth, not what was paid into it", () => {
    // $10,000 in, up $320, so the card leads with $10,320. Before this the
    // headline was the ledger balance, which meant adding up the cards could
    // never reach the net-worth total above them -- net worth includes the gain.
    show([account()]);

    expect(screen.getByText("$10,320.00")).toBeTruthy();
  });

  it("says what was paid in underneath, so the percentage can be checked", () => {
    // (+3.2%) is 320/10000. Without this line there is no number on the card the
    // reader could divide to get it.
    show([account()]);

    expect(screen.getByText("$10,000.00 paid in")).toBeTruthy();
  });

  it("is lower than what was paid in when the holding is down", () => {
    show([
      account({
        balance: 10_000,
        investment_return: {
          ...account().investment_return!,
          difference_amount: -810,
          return_percent: -8.1,
        },
      }),
    ]);

    expect(screen.getByText("$9,190.00")).toBeTruthy();
    expect(screen.getByText("$10,000.00 paid in")).toBeTruthy();
  });

  it("is the plain balance on an account with no reading", () => {
    show([account({ investment_return: null })]);

    expect(screen.getByText("$10,000.00")).toBeTruthy();
    expect(screen.queryByText(/paid in/)).toBeNull();
  });

  it("is the plain balance on a spending account, with no paid-in line", () => {
    // The change must not reach accounts that have no market value at all.
    show([account({ kind: "spending", name: "Chequing", investment_return: null })]);

    expect(screen.getByText("$10,000.00")).toBeTruthy();
    expect(screen.queryByText(/paid in/)).toBeNull();
  });
});

describe("the income share line", () => {
  it("names the share when there is one", () => {
    show([account({ income_share: 20 })]);

    expect(screen.getByText("20% of income")).toBeTruthy();
  });

  it("is absent entirely when there is no share", () => {
    // It used to say "no income share" on every card without one, which states the
    // absence of a setting rather than telling you anything.
    show([account({ income_share: 0 })]);

    expect(screen.queryByText(/income/)).toBeNull();
  });

  it("is absent at zero rather than rendering an empty line", () => {
    const { container } = show([account({ income_share: 0 })]);

    expect(container.querySelector(".sectorShare")).toBeNull();
  });

  it("still shows a fractional share", () => {
    // The guard is `> 0`, not truthiness on a rounded value.
    show([account({ income_share: 2.5 })]);

    expect(screen.getByText("2.5% of income")).toBeTruthy();
  });
});

describe("reordering", () => {
  const three = [
    account({ id: "a", name: "Chequing", kind: "spending", position: 0, investment_return: null }),
    account({ id: "b", name: "Savings", kind: "savings", position: 1, investment_return: null }),
    account({ id: "c", name: "Cash", kind: "spending", position: 2, investment_return: null }),
  ];

  function showReorderable(accounts: Account[], onReorder = vi.fn().mockResolvedValue(undefined)) {
    render(
      <MemoryRouter>
        <Sectors accounts={accounts} onEdit={vi.fn()} onAdd={vi.fn()} onReorder={onReorder} />
      </MemoryRouter>,
    );
    return onReorder;
  }

  it("writes only the accounts whose position changed", () => {
    expect(positionChanges(three, ["b", "a", "c"])).toEqual([
      { id: "b", position: 0 },
      { id: "a", position: 1 },
    ]);
  });

  it("writes every account when old ones share a position", () => {
    const tied = three.map((each) => ({ ...each, position: 0 }));
    expect(positionChanges(tied, ["a", "b", "c"])).toEqual([
      { id: "b", position: 1 },
      { id: "c", position: 2 },
    ]);
  });

  it("moves an account down one place with the arrow key on its handle", () => {
    const onReorder = showReorderable(three);
    fireEvent.keyDown(screen.getByRole("button", { name: "Reorder Chequing" }), { key: "ArrowDown" });
    expect(onReorder).toHaveBeenCalledWith(["b", "a", "c"]);
  });

  it("does nothing past either end", () => {
    const onReorder = showReorderable(three);
    fireEvent.keyDown(screen.getByRole("button", { name: "Reorder Chequing" }), { key: "ArrowUp" });
    fireEvent.keyDown(screen.getByRole("button", { name: "Reorder Cash" }), { key: "ArrowRight" });
    expect(onReorder).not.toHaveBeenCalled();
  });

  it("says it is saving, and disables the handles until it is done", async () => {
    let finish: () => void = () => {};
    const onReorder = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    showReorderable(three, onReorder);
    fireEvent.keyDown(screen.getByRole("button", { name: "Reorder Chequing" }), { key: "ArrowDown" });

    expect(screen.getByRole("status").textContent).toBe("Saving order…");
    expect((screen.getByRole("button", { name: "Reorder Savings" }) as HTMLButtonElement).disabled).toBe(true);

    finish();
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  });

  it("reports a failed save", async () => {
    showReorderable(three, vi.fn().mockRejectedValue(new Error("nope")));
    fireEvent.keyDown(screen.getByRole("button", { name: "Reorder Chequing" }), { key: "ArrowDown" });
    expect((await screen.findByRole("alert")).textContent).toMatch(/Couldn't save the new order/);
  });

  const realElementFromPoint = document.elementFromPoint;
  afterEach(() => { document.elementFromPoint = realElementFromPoint; });

  // jsdom does no layout, so the card under the pointer is stubbed: the test is
  // of what happens with it, not of hit-testing.
  function pointAt(name: string) {
    const card = screen.getByRole("button", { name: `Reorder ${name}` }).closest(".sectorCard");
    document.elementFromPoint = () => card;
  }

  it("drags a card onto another's place and saves that order on release", () => {
    const onReorder = showReorderable(three);
    const handle = screen.getByRole("button", { name: "Reorder Chequing" });
    fireEvent.pointerDown(handle, { pointerId: 1 });
    pointAt("Cash");
    fireEvent.pointerMove(handle, { pointerId: 1 });

    expect(handle.closest(".sectorCard")?.className).toContain("sectorCard--dragging");
    fireEvent.pointerUp(handle, { pointerId: 1 });
    expect(onReorder).toHaveBeenCalledWith(["b", "c", "a"]);
  });

  it("puts everything back when the drag is cancelled", () => {
    const onReorder = showReorderable(three);
    const handle = screen.getByRole("button", { name: "Reorder Chequing" });
    fireEvent.pointerDown(handle, { pointerId: 1 });
    pointAt("Cash");
    fireEvent.pointerMove(handle, { pointerId: 1 });
    fireEvent.keyDown(handle, { key: "Escape" });

    const names = screen.getAllByRole("button", { name: /Reorder/ }).map((each) => each.getAttribute("aria-label"));
    expect(names).toEqual(["Reorder Chequing", "Reorder Savings", "Reorder Cash"]);
    fireEvent.pointerUp(handle, { pointerId: 1 });
    expect(onReorder).not.toHaveBeenCalled();
  });

  it("saves nothing for a press on the handle that moves nowhere", () => {
    const onReorder = showReorderable(three);
    const handle = screen.getByRole("button", { name: "Reorder Savings" });
    fireEvent.pointerDown(handle, { pointerId: 1 });
    fireEvent.pointerUp(handle, { pointerId: 1 });
    expect(onReorder).not.toHaveBeenCalled();
  });

  it("offers no handle with a single account", () => {
    showReorderable([three[0]]);
    expect(screen.queryByRole("button", { name: /Reorder/ })).toBeNull();
  });

  it("offers no handle when nothing can save the order", () => {
    show(three);
    expect(screen.queryByRole("button", { name: /Reorder/ })).toBeNull();
  });

  it("keeps the handle out of the card's link, so a drag never opens the account", () => {
    showReorderable(three);
    const handle = screen.getByRole("button", { name: "Reorder Chequing" });
    expect(handle.closest("a")).toBeNull();
  });
});
