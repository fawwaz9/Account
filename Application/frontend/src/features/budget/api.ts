import { del, get, patch, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import {
  Account,
  AccountCreate,
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

export async function fetchTransactions(userId: string, accountId?: string) {
  const base = endpoints.finances.transactions(userId);
  return get<Transaction[]>(accountId ? `${base}?account_id=${accountId}` : base);
}

export async function createTransaction(userId: string, payload: TransactionCreate) {
  return post<Transaction>(endpoints.finances.transactions(userId), payload);
}

/** Returns both halves of the transfer. */
export async function createTransfer(userId: string, payload: TransferCreate) {
  return post<Transaction[]>(endpoints.finances.transfers(userId), payload);
}

export async function deleteTransaction(userId: string, transactionId: string) {
  return del<Transaction>(endpoints.finances.transaction(userId, transactionId));
}
