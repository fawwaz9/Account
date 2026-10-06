// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import Sectors from "./Sectors";
import Recurring from "./Recurring";
import EditAccountModal from "./EditAccountModal";
import { COUNTED_HELP, COUNTED_LABEL } from "../counting";
import { formatMoney } from "../money";
import { Account, UpcomingCharge } from "../types";

/** One switch per account for net worth and every analytic (Phase 1 D39). */

function account(over: Partial<Account> = {}): Account {
  return {
    id: "a1", name: "Chequing", kind: "spending", income_share: 100, archived: false, position: 0,
    counts_toward_net_worth: true, balance: 500, role_locked: false, ...over,
  } as Account;
}

function charge(over: Partial<UpcomingCharge>): UpcomingCharge {
  return {
    recurring_id: "r1", on_date: "2026-10-20", kind: "expense", amount: 100, signed_amount: -100,
    description: "Rent", account_id: "a1", account_name: "Chequing", to_account_id: null, category_id: null,
    ...over,
  } as UpcomingCharge;
}

afterEach(cleanup);

describe("an unticked account", () => {
  it("says so on its card, and only on its card", () => {
    render(
      <MemoryRouter>
        <Sectors accounts={[account(), account({ id: "a2", name: "Lent out", kind: "other", counts_toward_net_worth: false })]}
                 onEdit={vi.fn()} onAdd={vi.fn()} />
      </MemoryRouter>,
    );
    const tags = screen.getAllByText("not counted");
    expect(tags).toHaveLength(1);
    expect(tags[0].closest("a")!.textContent).toContain("Lent out");
  });

  it("stays listed among the standing instructions but leaves their totals", () => {
    const upcoming = [charge({}), charge({ recurring_id: "r2", description: "Loan back", account_id: "a2",
                                           account_name: "Lent out", amount: 250, signed_amount: -250 })];
    render(<Recurring rules={[]} upcoming={upcoming} onAdd={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()}
                      busy={false} uncounted={new Set(["a2"])} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain(`${formatMoney(100)} out`);
    expect(text).not.toContain(formatMoney(350));
    expect(text).toContain("Loan back");
  });

  it("is labelled in the edit dialog with the same words as Settings", () => {
    const acct = account();
    render(<EditAccountModal account={acct} accounts={[acct]} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByLabelText(COUNTED_LABEL)).toBeTruthy();
    expect(COUNTED_HELP).toMatch(/net worth and every figure/);
  });
});
