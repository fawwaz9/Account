import { del, get, patch, post, put } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import {
  Account,
  AccountActivity,
  AccountCreate,
  BudgetSummary,
  DepositCreate,
  DepositPreview,
  SpendCategory,
  Transaction,
  TransactionCreate,
  TransferCreate,
} from "./types";

export async function fetchAccounts(userId: string): Promise<Account[]> {
  return get<Account[]>(endpoints.finances.accounts(userId));
}

export async function createAccount(userId: string, payload: AccountCreate) {
  return post<Account>(endpoints.finances.accounts(userId), payload);
}

export async function updateAccount(
  userId: string,
  accountId: string,
  payload: Partial<AccountCreate>
) {
  return patch<Account>(endpoints.finances.account(userId, accountId), payload);
}

export async function deleteAccount(userId: string, accountId: string) {
  return del<Account>(endpoints.finances.account(userId, accountId));
}

/**
 * `start`/`end` bound occurred_on inclusively.
 *
 * Windowing on the server rather than filtering a fetched page matters: the
 * endpoint caps at 500 rows *after* ordering newest-first, so a client-side
 * filter would silently lose the oldest rows in the range.
 */
export async function fetchTransactions(
  userId: string,
  options: { accountId?: string; start?: string; end?: string } = {}
) {
  const query = [
    options.accountId ? `account_id=${options.accountId}` : null,
    options.start ? `start=${options.start}` : null,
    options.end ? `end=${options.end}` : null,
  ].filter(Boolean);

  const base = endpoints.finances.transactions(userId);
  return get<Transaction[]>(query.length ? `${base}?${query.join("&")}` : base);
}

/** One account's month: daily flow, totals, categories and its target. */
export async function fetchAccountActivity(
  userId: string,
  accountId: string,
  month: string
) {
  const base = endpoints.finances.accountActivity(userId, accountId);
  return get<AccountActivity>(`${base}?month=${month}`);
}

export async function createTransaction(userId: string, payload: TransactionCreate) {
  return post<Transaction>(endpoints.finances.transactions(userId), payload);
}

/** Returns both halves of the transfer. */
export async function createTransfer(userId: string, payload: TransferCreate) {
  return post<Transaction[]>(endpoints.finances.transfers(userId), payload);
}

export async function updateTransaction(
  userId: string,
  transactionId: string,
  payload: {
    amount?: number;
    description?: string | null;
    occurred_on?: string;
    category_id?: string | null;
  }
) {
  return patch<Transaction>(
    endpoints.finances.transaction(userId, transactionId),
    payload
  );
}

/**
 * `scope` decides how much of a grouped movement goes: "row" removes this one,
 * "group" removes every row sharing its group. Ignored for a transfer, which the
 * server always removes whole.
 */
export async function deleteTransaction(
  userId: string,
  transactionId: string,
  scope: "row" | "group" = "group"
) {
  const base = endpoints.finances.transaction(userId, transactionId);
  return del<Transaction>(`${base}?scope=${scope}`);
}

export async function fetchCategories(userId: string) {
  return get<SpendCategory[]>(endpoints.finances.categories(userId));
}

export async function createCategory(userId: string, name: string) {
  return post<SpendCategory>(endpoints.finances.categories(userId), {
    name,
    archived: false,
    position: 0,
  });
}

/** Removes the label only; the expenses it was on become uncategorised. */
export async function deleteCategory(userId: string, categoryId: string) {
  return del<SpendCategory>(endpoints.finances.category(userId, categoryId));
}

/** Sets what one account may spend in one month; replaces any existing target. */
export async function setBudgetTarget(
  userId: string,
  accountId: string,
  month: string,
  plannedAmount: number
) {
  return put<unknown>(endpoints.finances.budgetTargets(userId), {
    account_id: accountId,
    month,
    planned_amount: plannedAmount,
  });
}

export async function fetchBudgetSummary(userId: string, month: string) {
  return get<BudgetSummary>(`${endpoints.finances.budgetSummary(userId)}?month=${month}`);
}

/**
 * How a deposit would divide by the current income shares.
 *
 * Asked of the server rather than worked out here, so the cent-rounding rule
 * lives in one place and the preview always matches what recording writes.
 */
export async function previewDeposit(userId: string, amount: number) {
  return get<DepositPreview>(
    `${endpoints.finances.depositPreview(userId)}?amount=${amount}`
  );
}

export async function recordDeposit(userId: string, payload: DepositCreate) {
  return post<Transaction[]>(endpoints.finances.deposits(userId), payload);
}
