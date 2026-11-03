// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Account, Transaction } from "../types";

/**
 * Transfers carry a category (Phase 4 D27): money moved out of an account is
 * labelled like money spent. Each of the three places a transfer is written
 * offers the picker and sends what was picked.
 */

// Typed with real signatures, so `mock.calls[0]` has the payload at [1].
const createTransfer = vi.fn(async (_userId: string, _payload: Record<string, unknown>) => []);
const updateTransaction = vi.fn(
  async (_userId: string, _id: string, _payload: Record<string, unknown>) => ({}),
);
const createRecurring = vi.fn(async (_userId: string, _payload: Record<string, unknown>) => ({}));
vi.mock("../api", () => ({
  createTransaction: vi.fn(),
  createTransfer,
  previewDeposit: vi.fn(),
  recordDeposit: vi.fn(),
  updateTransaction,
  createRecurring,
  updateRecurring: vi.fn(),
}));
vi.mock("../../../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-1" } }),
}));
vi.mock("./CoursePicker", () => ({ default: () => null }));

const { default: AddMoneyModal } = await import("./AddMoneyModal");
const { default: EditTransactionModal } = await import("./EditTransactionModal");
const { default: RecurringModal } = await import("./RecurringModal");

const CATEGORIES = [
  { id: "cat-food", name: "Food", archived: false, position: 0 },
  { id: "cat-savings", name: "Savings", archived: false, position: 1 },
];

function account(id: string, name: string): Account {
  return {
    id, name, kind: "spending", income_share: 0, archived: false, position: 0,
    counts_toward_net_worth: true, balance: 0, role_locked: false, investment_return: null,
  } as Account;
}

const ACCOUNTS = [account("acct-chequing", "Chequing"), account("acct-savings", "Savings")];

const LEG: Transaction = {
  id: "row-1", kind: "transfer", account_id: "acct-savings", category_id: "cat-food",
  amount: 200, signed_amount: 200, description: "Top-up", occurred_on: "2026-10-06",
  group_id: "group-1", group_size: 2, course_id: null, tuition_payment_id: null,
};

beforeEach(() => {
  createTransfer.mockClear();
  updateTransaction.mockClear();
  createRecurring.mockClear();
});
afterEach(cleanup);

describe("a transfer's category", () => {
  it("is picked and sent when recording a transfer", async () => {
    render(
      <AddMoneyModal open accounts={ACCOUNTS} categories={CATEGORIES} courses={[]}
        onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "transfer" }));
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "200" } });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "cat-savings" } });
    fireEvent.submit(screen.getByLabelText("Amount").closest("form")!);

    await waitFor(() => expect(createTransfer).toHaveBeenCalledTimes(1));
    expect(createTransfer.mock.calls[0][1]).toMatchObject({
      from_account_id: "acct-chequing",
      to_account_id: "acct-savings",
      category_id: "cat-savings",
    });
  });

  it("is sent as null when left uncategorised", async () => {
    render(
      <AddMoneyModal open accounts={ACCOUNTS} categories={CATEGORIES} courses={[]}
        onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "transfer" }));
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "200" } });
    fireEvent.submit(screen.getByLabelText("Amount").closest("form")!);

    await waitFor(() => expect(createTransfer).toHaveBeenCalledTimes(1));
    expect(createTransfer.mock.calls[0][1]).toMatchObject({ category_id: null });
  });

  it("is shown and sent when editing either leg, with no course", async () => {
    render(
      <EditTransactionModal transaction={LEG} categories={CATEGORIES} courses={[]}
        onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    const picker = screen.getByLabelText("Category") as HTMLSelectElement;
    expect(picker.value).toBe("cat-food");
    expect(screen.getByText(/description and category/)).toBeDefined();

    fireEvent.change(picker, { target: { value: "cat-savings" } });
    fireEvent.submit(picker.closest("form")!);

    await waitFor(() => expect(updateTransaction).toHaveBeenCalledTimes(1));
    const payload = updateTransaction.mock.calls[0][2];
    expect(payload).toMatchObject({ category_id: "cat-savings" });
    expect(payload).not.toHaveProperty("course_id");
  });

  it("is offered on a standing transfer and kept when switching to one", async () => {
    render(
      <RecurringModal open rule={null} accounts={ACCOUNTS} categories={CATEGORIES}
        onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    const categoryPicker = () =>
      (screen.queryAllByRole("combobox") as HTMLSelectElement[]).find((select) =>
        Array.from(select.options).some((option) => option.value === "cat-savings"),
      );

    // Picked as an expense, then carried over to a transfer.
    fireEvent.change(categoryPicker()!, { target: { value: "cat-savings" } });
    fireEvent.click(screen.getByRole("button", { name: "Transfer" }));
    expect(categoryPicker()?.value).toBe("cat-savings");

    fireEvent.submit(categoryPicker()!.closest("form")!);
    await waitFor(() => expect(createRecurring).toHaveBeenCalledTimes(1));
    expect(createRecurring.mock.calls[0][1]).toMatchObject({ kind: "transfer", category_id: "cat-savings" });

    // Income carries none, so the picker goes.
    fireEvent.click(screen.getByRole("button", { name: "Income" }));
    expect(categoryPicker()).toBeUndefined();
  });
});
