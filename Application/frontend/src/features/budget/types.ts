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
}

export interface TransferCreate {
  from_account_id: string;
  to_account_id: string;
  amount: number;
  description: string | null;
  occurred_on: string;
}
