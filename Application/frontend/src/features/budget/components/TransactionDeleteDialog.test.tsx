// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Transaction } from "../types";

/**
 * Deleting a ledger row always asks first (audit H9), and a paycheque's share
 * never offers to go alone (audit H5). The × used to delete a row, or both
 * halves of a transfer, on one tap.
 */

const deleteTransaction = vi.fn(async (_userId: string, _id: string, _scope: string) => ({}));
vi.mock("../api", () => ({ deleteTransaction }));
vi.mock("../../../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-1" } }),
}));

const { useTransactionDelete } = await import("../hooks/useTransactionDelete");
const { default: TransactionDeleteDialog, deleteWording } = await import("./TransactionDeleteDialog");

function row(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: "t1", kind: "expense", account_id: "a1", category_id: null, amount: 12.5, signed_amount: -12.5,
    description: "Coffee", occurred_on: "2026-11-03", group_id: null, group_size: 1, course_id: null,
    tuition_payment_id: null, paycheque_id: null, recurring_id: null, ...overrides,
  };
}

/** A × button and the dialog, as the budget and account pages wire them. */
function Harness({ transaction }: { readonly transaction: Transaction }) {
  const remove = useTransactionDelete(async () => undefined);
  return (
    <>
      <button type="button" onClick={() => remove.requestDelete(transaction)}>×</button>
      <TransactionDeleteDialog remove={remove} />
    </>
  );
}

beforeEach(() => deleteTransaction.mockClear());
afterEach(cleanup);

describe("a tap on ×", () => {
  it("deletes nothing until the dialog is confirmed", async () => {
    render(<Harness transaction={row()} />);

    fireEvent.click(screen.getByRole("button", { name: "×" }));

    expect(screen.getByText("Delete this transaction?")).toBeTruthy();
    expect(deleteTransaction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleteTransaction).toHaveBeenCalledWith("user-1", "t1", "group"));
  });

  it("deletes nothing when cancelled", () => {
    render(<Harness transaction={row({ kind: "transfer", group_id: "g", group_size: 2 })} />);

    fireEvent.click(screen.getByRole("button", { name: "×" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByText("Delete this transfer?")).toBeNull();
    expect(deleteTransaction).not.toHaveBeenCalled();
  });

  it("never offers one share of a paycheque", async () => {
    render(<Harness transaction={row({ kind: "income", group_id: "g", group_size: 3, paycheque_id: "p1" })} />);

    fireEvent.click(screen.getByRole("button", { name: "×" }));

    expect(screen.queryByRole("button", { name: "Just this share" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Delete the cheque" }));
    await waitFor(() => expect(deleteTransaction).toHaveBeenCalledWith("user-1", "t1", "group"));
  });

  it("still offers one share of an ordinary split deposit", async () => {
    render(<Harness transaction={row({ kind: "income", group_id: "g", group_size: 3 })} />);

    fireEvent.click(screen.getByRole("button", { name: "×" }));
    fireEvent.click(screen.getByRole("button", { name: "Just this share" }));

    await waitFor(() => expect(deleteTransaction).toHaveBeenCalledWith("user-1", "t1", "row"));
  });
});

describe("the wording", () => {
  it("names the row, its amount and its day", () => {
    expect(deleteWording(row()).message).toMatch(/"Coffee", \$12\.50 on .*3 Nov\. This can't be undone\./);
  });

  it("says a transfer goes whole", () => {
    expect(deleteWording(row({ kind: "transfer", group_size: 2 })).message).toMatch(/Both sides/);
  });

  it("says the cheque goes with its shares", () => {
    const wording = deleteWording(row({ kind: "income", group_size: 3, paycheque_id: "p1" }));
    expect(wording.message).toMatch(/deletes the cheque from the Jobs page and all 3 of its shares/);
    expect(wording.offersShare).toBe(false);
  });

  it("says a standing payment won't write it again (audit C1)", () => {
    expect(deleteWording(row({ recurring_id: "r1" })).message).toMatch(/won't write it again/);
    expect(deleteWording(row()).message).not.toMatch(/standing/);
  });
});
