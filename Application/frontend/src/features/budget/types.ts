// Recurrence is defined once, in the calendar feature: one repeat rule serves
// class times and standing payments alike, and a second copy here would drift.
import { Recurrence } from "../calender/types";

export type AccountKind =
  | "spending"
  | "savings"
  | "investment"
  | "emergency"
  | "other";

export interface Account {
  id: string;
  name: string;
  kind: AccountKind;
  /** Default share of income, as a percentage */
  income_share: number;
  archived: boolean;
  position: number;
  /** Derived from the account's transactions, not stored */
  balance: number;
}

export interface AccountCreate {
  name: string;
  kind: AccountKind;
  income_share: number;
  archived: boolean;
  position: number;
}

export type TransactionKind = "income" | "expense" | "transfer";

export interface Transaction {
  id: string;
  kind: TransactionKind;
  account_id: string;
  category_id: string | null;
  /** Always positive */
  amount: number;
  /** Positive into the account, negative out of it */
  signed_amount: number;
  description: string | null;
  occurred_on: string;
  /** Present on both halves of a transfer */
  group_id: string | null;
  /** How many rows share this group; 1 when ungrouped */
  group_size: number;
}

export interface TransactionCreate {
  kind: "income" | "expense";
  account_id: string;
  amount: number;
  description: string | null;
  occurred_on: string;
  /** Only meaningful on expenses; the server ignores it on income */
  category_id: string | null;
}

export interface SpendCategory {
  id: string;
  name: string;
  archived: boolean;
  position: number;
}

export interface AccountBudget {
  account_id: string;
  account_name: string;
  planned: number;
  /** Expenses only -- transfers move money rather than spending it */
  actual: number;
  remaining: number;
  used_percent: number;
}

export interface CategorySpend {
  category_id: string | null;
  category_name: string;
  actual: number;
}

export interface BudgetSummary {
  month: string;
  total_planned: number;
  total_actual: number;
  accounts: AccountBudget[];
  by_category: CategorySpend[];
}

export interface TransferCreate {
  from_account_id: string;
  to_account_id: string;
  amount: number;
  description: string | null;
  occurred_on: string;
}

export interface DepositAllocation {
  account_id: string;
  amount: number;
}

export interface DepositPreview {
  amount: number;
  allocations: DepositAllocation[];
  /** True when no account carries an income share, so nothing can be split */
  needs_shares: boolean;
}

export interface DepositCreate {
  amount: number;
  occurred_on: string;
  description: string | null;
  /** Empty means split by each account's income share */
  allocations: DepositAllocation[];
}

export interface DayFlow {
  /** YYYY-MM-DD */
  day: string;
  money_in: number;
  money_out: number;
}

export interface BalancePoint {
  day: string;
  balance: number;
}

export interface AccountActivity {
  account_id: string;
  account_name: string;
  month: string;
  /** All-time, matching the account card */
  balance: number;
  total_in: number;
  total_out: number;
  net: number;
  transaction_count: number;
  planned: number;
  remaining: number;
  used_percent: number;
  /** One entry per day of the month, zero-filled */
  daily: DayFlow[];
  by_category: CategorySpend[];
  /** All time, one point per day that had movement */
  balance_history: BalancePoint[];
}

/* ===== Standing instructions ===== */

/** The four shapes money moves in, matching the money dialog's tabs. */
export type RecurringKind = "income" | "expense" | "transfer" | "deposit";

/**
 * A standing instruction: rent on the 1st, Spotify on the 14th.
 *
 * Stores the rule, never the payments. An occurrence on or before today is
 * written as a real transaction; one after today stays a projection, because a
 * balance is the sum of its rows and money that has not moved must not be in it.
 */
export interface RecurringTransaction {
  id: string;
  kind: RecurringKind;
  amount: number;
  description: string | null;
  /** The pot it comes from, or the source of a transfer. Null for a deposit. */
  account_id: string | null;
  to_account_id: string | null;
  category_id: string | null;
  starts_on: string;
  recurrence: Recurrence;
  active: boolean;
  skipped_dates: string[];
  /** The most recent date already charged, or null if it never has been. */
  last_run_on: string | null;
  /** The next date owed, or null once the rule has run out. */
  next_due_on: string | null;
}

export interface RecurringCreate {
  kind: RecurringKind;
  amount: number;
  description: string | null;
  account_id: string | null;
  to_account_id: string | null;
  category_id: string | null;
  starts_on: string;
  recurrence: Recurrence;
  active: boolean;
}

export type RecurringUpdate = Partial<
  Pick<RecurringCreate, "amount" | "description" | "category_id" | "starts_on" | "recurrence" | "active">
>;

/** A payment the rules say is coming. Never a ledger row — nothing has moved. */
export interface UpcomingCharge {
  recurring_id: string;
  on_date: string;
  kind: RecurringKind;
  amount: number;
  /** Negative for money leaving, so projections and balances sum alike. */
  signed_amount: number;
  description: string | null;
  account_id: string | null;
  account_name: string | null;
  to_account_id: string | null;
  category_id: string | null;
}

/** What materialising due payments actually did. */
export interface RecurringRun {
  created: number;
  transactions: Transaction[];
  /** Rules that could not run, and why. One broken rule does not stop the rest. */
  skipped: string[];
}
