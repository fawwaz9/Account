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
  /** What it was bought for, on expenses. Tuition never sets this. */
  course_id: string | null;
  /** Set when a tuition payment owns this row, so it opens the right editor. */
  tuition_payment_id: string | null;
}

export interface TransactionCreate {
  kind: "income" | "expense";
  account_id: string;
  amount: number;
  description: string | null;
  occurred_on: string;
  /** Only meaningful on expenses; the server ignores it on income */
  category_id: string | null;
  /** Which course this was bought for. Expense-only, like the category. */
  course_id: string | null;
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

/** One deduction on a tuition bill: money that lowered it without being income. */
export interface TuitionDeduction {
  description: string;
  amount: number;
}

export interface TuitionCourse {
  course_id: string;
  code: string;
  name: string;
  credits: number;
  share: number;
}

/**
 * The arithmetic of a tuition payment, before anything is written.
 *
 * Both totals are here on purpose. `gross` is what the term is worth and is what
 * the course pages will report; `payable` is what leaves the account. They are
 * different numbers and the form shows both rather than implying one.
 */
export interface TuitionPreview {
  school_year: number | null;
  semester: string | null;
  /** The term as a person would write it; school_year is a year of standing. */
  term_name: string;
  courses: TuitionCourse[];
  credits_counted: number;
  cost_per_credit: number;
  gross: number;
  fees: number;
  deductions_total: number;
  payable: number;
  /** Rate already recorded this term, so instalments are visibly additive. */
  already_recorded_per_credit: number;
  can_record: boolean;
  reason: string | null;
}

export interface TuitionCreate {
  account_id: string;
  occurred_on: string;
  cost_per_credit: number;
  fees: number;
  description: string | null;
  deductions: TuitionDeduction[];
}

export interface TuitionPayment {
  id: string;
  transaction_id: string;
  school_year: number | null;
  semester: string | null;
  cost_per_credit: number;
  fees: number;
  credits_counted: number;
  occurred_on: string;
  deductions: TuitionDeduction[];
}

export interface TuitionUpdate extends TuitionCreate {
  /** Re-count the term's credits as they stand now, rather than as billed. */
  recount_credits: boolean;
}

export interface CourseCostLine {
  label: string;
  amount: number;
}

/** What a course cost: gross tuition share plus anything bought for it. */
export interface CourseCost {
  course_id: string;
  credits: number;
  cost_per_credit: number;
  tuition_share: number;
  materials: CourseCostLine[];
  materials_total: number;
  total: number;
}

/**
 * What a term cost, measured over the term rather than a calendar month.
 *
 * A month is the wrong unit for a student: tuition lands once and textbooks land
 * in the first fortnight. Grades knows when a term runs, per course, so the span
 * is assembled from the courses in it.
 */
export interface TermBudget {
  term_name: string;
  /** null when no course in the term carries dates; `reason` then says why. */
  starts_on: string | null;
  ends_on: string | null;
  dated_courses: number;
  undated_courses: number;
  spent: number;
  received: number;
  net: number;
  /** Spend tagged to a course in this term, tuition included. */
  on_courses: number;
  by_category: CategorySpend[];
  days_elapsed: number;
  days_total: number;
  can_measure: boolean;
  reason: string | null;
}
