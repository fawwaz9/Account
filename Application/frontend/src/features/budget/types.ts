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
