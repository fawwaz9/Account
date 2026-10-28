// Recurrence is defined once, in the calendar feature: one repeat rule serves
// class times and standing payments alike, and a second copy here would drift.
import { Recurrence } from "../calender/types";

/** Kinds of money account; the kind gives an account its roles. */
export type AccountKind =
  | "spending"
  | "savings"
  | "investment"
  | "emergency"
  | "other"
  /** Money owed: its balance reads negative, so any total of balances subtracts it. */
  | "debt";

/**
 * An investment's latest reading: how far its value sits above or below the ledger.
 * A level, not a month's gain: never sum a list of these.
 */
export interface InvestmentReturn {
  /** Market value less ledger balance; positive is up. */
  difference_amount: number;
  /** Server-rounded percent of `ledger_balance`; null when that is zero or negative. */
  return_percent: number | null;
  /** Month the reading is for, YYYY-MM-01. */
  as_of: string;
  /** No reading for the month shown, so the last one stands in; the UI must date it. */
  is_carried_forward: boolean;
  /** Balance the percentage was measured against. */
  ledger_balance: number;
  /** Value as typed, so a form can show it back. */
  market_value: number | null;
  /** Movement during the month asked for; null when unknowable, which is not zero. */
  month_gain: number | null;
}

/** A money account with its derived balance. */
export interface Account {
  id: string;
  name: string;
  kind: AccountKind;
  /** Default share of income, percent. */
  income_share: number;
  archived: boolean;
  position: number;
  /** Counted account: false leaves it out of every multi-account figure. */
  counts_toward_net_worth: boolean;
  /** Signed sum of its transactions, derived on read. */
  balance: number;
  /** Last active account of a kind the app needs: no delete, archive or change of kind. */
  role_locked: boolean;
  /** Latest reading overall; null unless an investment account has one. */
  investment_return: InvestmentReturn | null;
}

/** The net worth headline. */
export interface NetWorth {
  /** Counted balances plus each investment's latest gain; debt is already negative. */
  net_worth: number;
  /** Debt as a positive figure, for display. */
  debt_total: number;
  /** Part of `net_worth` that is investment gain, disclosed beside the headline. */
  investment_gain: number;
}

/** Body to create an account. */
export interface AccountCreate {
  name: string;
  kind: AccountKind;
  income_share: number;
  archived: boolean;
  position: number;
  counts_toward_net_worth?: boolean;
}

/** What a ledger row records. */
export type TransactionKind = "income" | "expense" | "transfer";

/** One ledger row, sent as a magnitude plus its signed amount. */
export interface Transaction {
  id: string;
  kind: TransactionKind;
  account_id: string;
  category_id: string | null;
  /** Magnitude, always positive. */
  amount: number;
  /** Positive into the account, negative out of it. */
  signed_amount: number;
  description: string | null;
  occurred_on: string;
  /** Ties a transfer's two rows or a deposit's allocations; null when alone. */
  group_id: string | null;
  /** Rows sharing `group_id`; 1 when ungrouped. */
  group_size: number;
  /** Course an expense was bought for; tuition never sets it. */
  course_id: string | null;
  /** Set when a tuition payment owns this row, so it opens that editor. */
  tuition_payment_id: string | null;
}

/** Body to record income or an expense. */
export interface TransactionCreate {
  kind: "income" | "expense";
  account_id: string;
  amount: number;
  description: string | null;
  occurred_on: string;
  /** Expense category; ignored on income. */
  category_id: string | null;
  /** Course it was bought for; expenses only. */
  course_id: string | null;
}

/** A spending category. */
export interface SpendCategory {
  id: string;
  name: string;
  archived: boolean;
  position: number;
}

/** One account's month: planned against actual spending. */
export interface AccountBudget {
  account_id: string;
  account_name: string;
  planned: number;
  /** Expenses plus outgoing transfers this month. */
  actual: number;
  remaining: number;
  used_percent: number;
  /** `planned` is the sum of category limits, so it is shown but not editable. */
  planned_is_derived: boolean;
}

/** One category's spending for the month, with its limit where known. */
export interface CategorySpend {
  category_id: string | null;
  category_name: string;
  actual: number;
  /** Monthly limit, sent only on an account's own page; null for none or Uncategorised. */
  limit: number | null;
  /** Limit less actual; negative is overspent, 0 with no limit. */
  remaining: number;
  /** Server's percent, not clamped, so a bar can go red past 100. */
  used_percent: number;
  /** This month's limit differs from the account's standing one. */
  limit_is_override: boolean;
}

/** A month's budget across every account. */
export interface BudgetSummary {
  month: string;
  total_planned: number;
  total_actual: number;
  accounts: AccountBudget[];
  by_category: CategorySpend[];
}

/** Body to move money between two accounts. */
export interface TransferCreate {
  from_account_id: string;
  to_account_id: string;
  amount: number;
  description: string | null;
  occurred_on: string;
}

/** One account's part of a deposit. */
export interface DepositAllocation {
  account_id: string;
  amount: number;
}

/** How a deposit would split, before it is recorded. */
export interface DepositPreview {
  amount: number;
  allocations: DepositAllocation[];
  /** No account has an income share, so nothing can be split. */
  needs_shares: boolean;
}

/** Body to record income split across accounts. */
export interface DepositCreate {
  amount: number;
  occurred_on: string;
  description: string | null;
  /** Explicit split; empty splits by income share. */
  allocations: DepositAllocation[];
}

/** Money in and out on one day. */
export interface DayFlow {
  day: string;
  money_in: number;
  money_out: number;
}

/** Balance at the end of a day with movement. */
export interface BalancePoint {
  day: string;
  balance: number;
}

/** One account's month: totals, daily flow, categories and balance history. */
export interface AccountActivity {
  account_id: string;
  account_name: string;
  month: string;
  /** Account kind, so the page shows the tiles that fit it. */
  kind: AccountKind;
  /** All-time balance, matching the account card. */
  balance: number;
  total_in: number;
  total_out: number;
  net: number;
  transaction_count: number;
  planned: number;
  remaining: number;
  used_percent: number;
  /** `planned` is the sum of category limits, so it is shown but not editable. */
  planned_is_derived: boolean;
  /** One entry per day of the month, zero-filled. */
  daily: DayFlow[];
  by_category: CategorySpend[];
  /** All time, one point per day with movement. */
  balance_history: BalancePoint[];
  /** Reading for the month shown, carried forward if needed; null if not an investment. */
  investment_return: InvestmentReturn | null;
  /** Latest reading against the all-time balance; the header uses this one. */
  all_time_return: InvestmentReturn | null;
  /** Ledger balance at the month's end, or today for the current month. */
  ledger_balance_at_month: number;
}

/* ===== Standing instructions ===== */

/** The four shapes a standing instruction takes, as in the money dialog's tabs. */
export type RecurringKind = "income" | "expense" | "transfer" | "deposit";

/** Standing instruction: the rule only; each payment is written once it falls due. */
export interface RecurringTransaction {
  id: string;
  kind: RecurringKind;
  amount: number;
  description: string | null;
  /** Paying account, or a transfer's source; null for a deposit. */
  account_id: string | null;
  to_account_id: string | null;
  category_id: string | null;
  starts_on: string;
  recurrence: Recurrence;
  active: boolean;
  /** Occurrences cancelled one at a time. */
  skipped_dates: string[];
  /** Latest date already written; null if never. */
  last_run_on: string | null;
  /** Next date owed; null once the rule has run out. */
  next_due_on: string | null;
}

/** Body to create a standing instruction. */
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

/** Fields a standing instruction can change after creation. */
export type RecurringUpdate = Partial<
  Pick<RecurringCreate, "amount" | "description" | "category_id" | "starts_on" | "recurrence" | "active">
>;

/** A payment a rule says is coming: a projection, never a ledger row. */
export interface UpcomingCharge {
  recurring_id: string;
  on_date: string;
  kind: RecurringKind;
  amount: number;
  /** Negative for money leaving, so projections sum like balances. */
  signed_amount: number;
  description: string | null;
  account_id: string | null;
  account_name: string | null;
  to_account_id: string | null;
  category_id: string | null;
}

/** What the catch-up run wrote. */
export interface RecurringRun {
  created: number;
  transactions: Transaction[];
  /** Rules that could not run, with why; one broken rule does not stop the rest. */
  skipped: string[];
}

/** A deduction on a tuition bill, such as a bursary: lowers it without being income. */
export interface TuitionDeduction {
  description: string;
  amount: number;
}

/** A course a tuition payment covers. */
export interface TuitionCourse {
  course_id: string;
  code: string;
  name: string;
  credits: number;
  /** Dollars of the gross its credits account for. */
  share: number;
}

/**
 * A tuition payment's arithmetic before anything is written.
 * `gross` is what the term is worth; `payable` is what leaves the account.
 */
export interface TuitionPreview {
  school_year: number | null;
  semester: string | null;
  /** Term as a person writes it; `school_year` is a year of standing. */
  term_name: string;
  courses: TuitionCourse[];
  credits_counted: number;
  cost_per_credit: number;
  /** Credits times rate, before fees and deductions. */
  gross: number;
  fees: number;
  deductions_total: number;
  payable: number;
  /** Rate already recorded this term; instalments add up. */
  already_recorded_per_credit: number;
  can_record: boolean;
  /** Why it cannot be recorded, when `can_record` is false. */
  reason: string | null;
}

/** Body to record a tuition payment. */
export interface TuitionCreate {
  account_id: string;
  occurred_on: string;
  /** The rate, not the total; a term's payments add up. */
  cost_per_credit: number;
  fees: number;
  description: string | null;
  deductions: TuitionDeduction[];
}

/** A recorded tuition payment; it owns one ledger row. */
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

/** Body to edit a tuition payment. */
export interface TuitionUpdate extends TuitionCreate {
  /** Recount the term's credits as they stand now, not as billed. */
  recount_credits: boolean;
}

/** One item bought for a course. */
export interface CourseCostLine {
  label: string;
  amount: number;
}

/** What a course cost: its gross tuition share plus anything bought for it. */
export interface CourseCost {
  course_id: string;
  credits: number;
  cost_per_credit: number;
  tuition_share: number;
  materials: CourseCostLine[];
  materials_total: number;
  total: number;
}

/** What a term cost, measured over its span rather than a calendar month. */
export interface TermBudget {
  term_name: string;
  /** Null when no course in the term has dates; `reason` says why. */
  starts_on: string | null;
  ends_on: string | null;
  dated_courses: number;
  undated_courses: number;
  spent: number;
  received: number;
  net: number;
  /** Spending tagged to this term's courses, tuition included. */
  on_courses: number;
  by_category: CategorySpend[];
  days_elapsed: number;
  days_total: number;
  can_measure: boolean;
  reason: string | null;
}

/* ===== Safe to spend ===== */

/** Mirrors app/Finances/schemas/safe.py. */

/** A spending account counted in safe-to-spend. */
export interface SpendableAccount {
  account_id: string;
  name: string;
  balance: number;
}

/** A payment due before the window ends. */
export interface Commitment {
  on_date: string;
  description: string | null;
  /** Positive; every commitment reduces what is safe. */
  amount: number;
}

/** Safe-to-spend until the next payday, with its workings. */
export interface SafeToSpend {
  /** Today. */
  starts_on: string;
  /** Day before the next pay date, or month end when no job has a pay rule. */
  ends_on: string;
  days: number;
  /** The window ends at a real pay date, not the fallback. */
  until_payday: boolean;

  spendable: number;
  committed: number;
  /** This period's sinking-fund contributions not yet transferred. */
  earmarked: number;
  /** The answer: spendable less committed and earmarked. */
  safe_now: number;

  /** Confirmed work no cheque has covered yet; context, never the headline. */
  owed_to_you: number;
  /** `safe_now` plus `owed_to_you`. */
  safe_soon: number;

  /** Safe per remaining day; null when `safe_now` is negative. */
  per_day: number | null;

  accounts: SpendableAccount[];
  commitments: Commitment[];
}

/* ===== Sinking funds ===== */

/** Mirrors app/Finances/schemas/sinking.py. */

/** One month's transfer into a sinking fund. */
export interface SinkingContribution {
  id: string;
  /** First of the month it counts for. */
  for_month: string;
  amount: number;
  /** The transfer's group; null only if that transfer was deleted. */
  group_id: string | null;
  confirmed_at: string | null;
}

/** Sinking fund: a target by a due date, its monthly need derived on read. */
export interface SinkingFund {
  id: string;
  name: string;
  target_amount: number;
  due_on: string;
  from_account_id: string;
  to_account_id: string;
  archived: boolean;
  created_at: string | null;

  /** Transferred so far. */
  saved: number;
  remaining: number;
  /** Contributions left, counting this month; 0 once past due. */
  months_left: number;
  /** Monthly need, derived on every read, so a missed month corrects itself. */
  per_month: number;
  funded_this_month: boolean;
  /** This month's contribution while still unpaid; safe-to-spend subtracts it. */
  unfunded_this_month: number;
  overdue: boolean;

  contributions: SinkingContribution[];
}

/** Body to create a sinking fund. */
export interface SinkingFundCreate {
  name: string;
  target_amount: number;
  due_on: string;
  from_account_id: string;
  to_account_id: string;
  archived: boolean;
}

/** Partial sinking-fund edit. */
export type SinkingFundUpdate = Partial<SinkingFundCreate>;

/** Body to transfer this month's contribution. */
export interface ContributionRequest {
  /** Null uses the derived monthly figure; a smaller amount is allowed. */
  amount: number | null;
  occurred_on: string | null;
}

/* ===== Subscription audit =====
   Mirrors app/Finances/schemas/subscription.py. Nothing here is stored --
   every fetch re-derives the pattern from the ledger, so there is no id to
   dismiss by, only charges to act on. */

/** How often a detected subscription charges. */
export type SubscriptionCadence = "weekly" | "fortnightly" | "monthly";

/** One charge in a detected subscription. */
export interface SubscriptionOccurrence {
  transaction_id: string;
  on_date: string;
  amount: number;
}

/** A repeating charge spotted in the ledger; derived on each fetch, never stored. */
export interface SubscriptionCandidate {
  /** Latest charge's own text, so it matches the ledger. */
  description: string;
  account_id: string;
  category_id: string | null;
  cadence: SubscriptionCadence;
  median_amount: number;
  first_seen: string;
  last_seen: string;
  next_expected_on: string;
  occurrences: SubscriptionOccurrence[];
  /** Ready-to-submit standing instruction, for confirming it. */
  suggested: RecurringCreate;
}

/* ===== Cash-flow forecast (Phase 1 item 9) ===== */

/** Spending-account balance at the end of a day. */
export interface ForecastPoint {
  on_date: string;
  balance: number;
}

/** A dated movement the forecast expects: a standing instruction or pay. */
export interface ForecastEvent {
  on_date: string;
  description: string;
  /** Signed: negative leaves the spending accounts. */
  amount: number;
  source: "recurring" | "pay";
  /** Divided by the income split on the way in. */
  split: boolean;
}

/** How long held money lasts at the recent pace. */
export interface Runway {
  /** Spending, savings and emergency balances; no investments or debt. */
  liquid: number;
  /** Average net money out per day, all accounts. */
  daily_burn: number;
  /** Null when nothing is burning or there is nothing to burn. */
  lasts_until: string | null;
}

/** One merchant's one-off spending, projected to the horizon. */
export interface MerchantRunRate {
  merchant: string;
  /** Total over the look-back. */
  spent: number;
  occurrences: number;
  /** That pace carried to the forecast's end. */
  projected: number;
}

/** Forecast: projected spending-account balance to the term's end. */
export interface CashFlowForecast {
  starts_on: string;
  ends_on: string;
  /** False when the term is unknown and sixteen weeks stand in. */
  ends_at_term_end: boolean;
  starting_balance: number;
  /** Average one-off spending per day, from spending accounts. */
  daily_spending: number;
  /** Days of history behind that average. */
  spending_history_days: number;
  points: ForecastPoint[];
  events: ForecastEvent[];
  /** First day the balance goes below zero; null if it never does. */
  negative_on: string | null;
  lowest_balance: number;
  lowest_on: string;
  ending_balance: number;
  runway: Runway | null;
  run_rates: MerchantRunRate[];
  assumptions: string[];
}

/* ===== Year plan and hours-to-goal (Phase 1 item 10) ===== */

/** One month of the year plan. */
export interface PlanMonth {
  /** First of the month. */
  month: string;
  money_in: number;
  /** Positive: what leaves. */
  money_out: number;
  /** Liquid balance on the month's last day. */
  end_balance: number;
}

/** End balance with this many extra hours a week. */
export interface PlanScenario {
  extra_hours_per_week: number;
  end_balance: number;
}

/** Hours-to-goal: extra weekly work needed to reach a target. */
export interface PlanGoal {
  target: number;
  target_on: string;
  /** Where the plan ends with no extra work. */
  base_end_balance: number;
  /** Negative when the target is already met. */
  shortfall: number;
  /** Hourly job the extra hours are priced at. */
  job_name: string;
  /** What one extra hour adds to liquid money, after deductions and shares. */
  net_hourly: number;
  weeks: number;
  /** Null when the target is already met. */
  extra_hours_per_week: number | null;
  scenarios: PlanScenario[];
}

/** Year plan: liquid balance month by month to the school year's end. */
export interface AnnualPlan {
  starts_on: string;
  ends_on: string;
  starting_balance: number;
  months: PlanMonth[];
  ending_balance: number;
  lowest_balance: number;
  lowest_on: string;
  /** Present when a target was asked for and an hourly job can price it. */
  goal: PlanGoal | null;
  assumptions: string[];
}

/* ===== The plan against what happened (Phase 1 D37) ===== */

/** A saved copy of the year plan. */
export interface SavedPlan {
  id: string;
  saved_on: string;
  starts_on: string;
  ends_on: string;
}

/** One finished month against the newest plan saved before it began. */
export interface MonthReview {
  month: string;
  plan_saved_on: string;
  planned_in: number;
  planned_out: number;
  planned_end: number;
  actual_in: number;
  actual_out: number;
  actual_end: number;
  /** Part of `actual_out`; the plan leaves tuition out. */
  tuition_out: number;
}

/** Saved plans compared with what happened. */
export interface PlanReview {
  latest: SavedPlan | null;
  months: MonthReview[];
}

/* ===== CSV import (Phase 1 item 7) ===== */

/** Which CSV column means what; detected, then adjustable. */
export interface ImportMapping {
  has_header: boolean;
  /** Column index of the date. */
  date: number;
  /** Columns joined to make the description. */
  description: number[];
  /** One signed amount column, or null to use `debit` and `credit`. */
  amount: number | null;
  debit: number | null;
  credit: number | null;
  /** Order for ambiguous dates like 03/04. */
  date_order: "mdy" | "dmy";
  /** Flip every amount, for card exports that list purchases as positive. */
  invert: boolean;
}

/** One parsed CSV line and what importing it would do. */
export interface ImportRow {
  /** 1-based line in the file; a commit names rows by it. */
  line: number;
  on_date: string | null;
  description: string;
  /** Signed: negative is money out. */
  amount: number | null;
  status: "new" | "duplicate" | "error";
  /** Existing row a duplicate matches. */
  duplicate_of: string | null;
  reason: string | null;
  /** Suggested expense category, or null to ask. */
  category_id: string | null;
  /** Where the suggestion came from. */
  category_source: "learned" | "rule" | "bayes" | null;
}

/** A CSV import before it is committed. */
export interface ImportPreview {
  account_id: string;
  mapping: ImportMapping;
  /** Header cells, so column indexes have names. */
  columns: string[];
  /** Every date reads either way; the person should confirm the order. */
  date_order_assumed: boolean;
  rows: ImportRow[];
  new_count: number;
  duplicate_count: number;
  error_count: number;
  money_in: number;
  money_out: number;
}

/** A committed import, undoable while its rows remain. */
export interface ImportSummary {
  id: string;
  account_id: string;
  account_name: string;
  filename: string | null;
  created_at: string;
  /** Rows written at the time. */
  row_count: number;
  /** Still in the ledger: what undo would remove. */
  rows_remaining: number;
  first_date: string | null;
  last_date: string | null;
  /** Subscriptions the audit now sees; only on the commit's answer. */
  subscription_candidates: number | null;
}
