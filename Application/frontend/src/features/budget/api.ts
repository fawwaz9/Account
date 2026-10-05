import { del, get, patch, post, put } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import {
  ContributionRequest,
  SinkingFund,
  SinkingFundCreate,
  SinkingFundUpdate,
  SafeToSpend,
  CashFlowForecast,
  AnnualPlan,
  SubscriptionCandidate,
  Account,
  AccountActivity,
  AccountCreate,
  NetWorth,
  BudgetSummary,
  DepositCreate,
  DepositPreview,
  RecurringCreate,
  RecurringRun,
  RecurringTransaction,
  RecurringUpdate,
  CourseCost,
  SpendCategory,
  TermBudget,
  Transaction,
  TransactionCreate,
  TransferCreate,
  TuitionCreate,
  TuitionPayment,
  TuitionPreview,
  TuitionUpdate,
  UpcomingCharge,
} from "./types";

/**
 * What counts, less what is owed. Computed on the server because two screens
 * show it -- this page and the dashboard -- and a rule about which accounts
 * count is exactly the kind that drifts when it is written twice.
 */
export async function fetchNetWorth(userId: string): Promise<NetWorth> {
  return get<NetWorth>(endpoints.finances.netWorth(userId));
}

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
 * Record what an investment account's holding is worth, for one month.
 *
 * Sends the market value -- the figure off a statement -- and the server stores
 * how far that sits above the month's ledger balance. An upsert, so saving the
 * same month twice corrects it instead of failing.
 *
 * Returns the whole account, so the card's figure comes back in this response
 * rather than needing a second fetch.
 */
export async function setAccountMonthValue(
  userId: string,
  accountId: string,
  month: string,
  marketValue: number
) {
  return put<Account>(endpoints.finances.accountMonthValue(userId, accountId), {
    month,
    market_value: marketValue,
  });
}

/** Forget one month's reading. The month is required, never defaulted. */
export async function clearAccountMonthValue(
  userId: string,
  accountId: string,
  month: string
) {
  return del<Account>(
    `${endpoints.finances.accountMonthValue(userId, accountId)}?month=${month}`
  );
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

/**
 * Rename or archive a category. The PATCH route has existed since categories
 * were built; this function is what was missing, which is why nothing could
 * edit one.
 */
export async function updateCategory(
  userId: string,
  categoryId: string,
  payload: { name?: string; archived?: boolean; position?: number }
) {
  return patch<SpendCategory>(endpoints.finances.category(userId, categoryId), payload);
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

/**
 * Set what one account may spend on one category, or clear it with `null`.
 *
 * `null` removes the limit rather than setting one of zero -- and if it was the
 * account's last, the account goes back to the target typed into Planned spend.
 * Sending `0` instead would close the category *and* keep the account derived.
 */
export async function setAccountCategoryLimit(
  userId: string,
  accountId: string,
  categoryId: string,
  limitAmount: number | null,
  /** Null sets the standing limit; a month sets that month's override only. */
  month: string | null = null
) {
  return put<unknown>(endpoints.finances.accountCategoryLimits(userId), {
    account_id: accountId,
    category_id: categoryId,
    month,
    limit_amount: limitAmount,
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

/* ===== Standing instructions ===== */

export async function fetchRecurring(userId: string, includeInactive = true) {
  const base = endpoints.finances.recurring(userId);
  return get<RecurringTransaction[]>(`${base}?include_inactive=${includeInactive}`);
}

export async function createRecurring(userId: string, payload: RecurringCreate) {
  return post<RecurringTransaction>(endpoints.finances.recurring(userId), payload);
}

export async function updateRecurring(
  userId: string,
  ruleId: string,
  payload: RecurringUpdate
) {
  return patch<RecurringTransaction>(endpoints.finances.recurringRule(userId, ruleId), payload);
}

/** Stops the instruction. Payments it already made stay — they are real. */
export async function deleteRecurring(userId: string, ruleId: string) {
  return del<RecurringTransaction>(endpoints.finances.recurringRule(userId, ruleId));
}

/**
 * Write every payment that is owed and has not been written yet.
 *
 * Idempotent — a payment is keyed by (rule, date) — so calling it on every
 * budget load is safe, and is what makes last month's rent already be there
 * when you open the app, with no scheduler anywhere.
 */
export async function runRecurring(userId: string) {
  return post<RecurringRun>(endpoints.finances.recurringRun(userId), {});
}

/** What is committed but has not happened. Projections, never ledger rows. */
export async function fetchUpcoming(userId: string, start: string, end: string) {
  const base = endpoints.finances.recurringUpcoming(userId);
  return get<UpcomingCharge[]>(`${base}?start=${start}&end=${end}`);
}

/** Skip one payment — a month a subscription was paused — without ending it. */
export async function skipRecurring(userId: string, ruleId: string, onDate: string) {
  return post<RecurringTransaction>(
    `${endpoints.finances.recurringSkip(userId, ruleId)}?on_date=${onDate}`,
    {}
  );
}

/** Which course a line of text names, decided server-side. See CoursePicker. */
export async function resolveCourse(userId: string, text: string) {
  return get<{ course_id: string | null; code: string | null; name: string | null }>(
    `${endpoints.grades.resolveCourse(userId)}?text=${encodeURIComponent(text)}`
  );
}

/** The arithmetic of a tuition payment, before anything is written. */
export async function fetchTuitionPreview(
  userId: string,
  costPerCredit: number,
  fees: number,
  deductionsTotal: number
) {
  const query = new URLSearchParams({
    cost_per_credit: String(costPerCredit),
    fees: String(fees),
    deductions_total: String(deductionsTotal),
  });
  return get<TuitionPreview>(`${endpoints.finances.tuitionPreview(userId)}?${query}`);
}

export async function recordTuition(userId: string, data: TuitionCreate) {
  return post(endpoints.finances.tuition(userId), data);
}

/** What a course cost: its gross tuition share plus anything bought for it. */
export async function fetchCourseCost(userId: string, courseId: string) {
  return get<CourseCost>(endpoints.finances.courseCost(userId, courseId));
}

export async function fetchTuitionPayment(userId: string, paymentId: string) {
  return get<TuitionPayment>(endpoints.finances.tuitionPayment(userId, paymentId));
}

/** Correct a payment. Its ledger row moves with it. */
export async function updateTuition(
  userId: string,
  paymentId: string,
  data: TuitionUpdate
) {
  return patch<TuitionPayment>(
    endpoints.finances.tuitionPayment(userId, paymentId),
    data
  );
}

/** Remove a payment and the ledger row it owns. */
export async function deleteTuition(userId: string, paymentId: string) {
  return del(endpoints.finances.tuitionPayment(userId, paymentId));
}

/** What the current term has cost, over the term's own dates. */
export async function fetchTermBudget(userId: string) {
  return get<TermBudget>(endpoints.finances.termBudget(userId));
}

/**
 * What can be spent between now and the next time money arrives.
 *
 * Two figures come back. `safe_now` is the answer -- cash in a spending account
 * less what is committed. `safe_soon` adds confirmed work not yet paid for, and
 * is context rather than a second answer.
 */
export async function fetchSafeToSpend(userId: string) {
  return get<SafeToSpend>(endpoints.finances.safeToSpend(userId));
}

/** Where the spending accounts are heading, to the end of the term. */
export async function fetchForecast(userId: string) {
  return get<CashFlowForecast>(endpoints.finances.forecast(userId));
}

/** The year as one running balance; with a target, the weekly hours it takes. */
export async function fetchPlan(userId: string, target?: number, until?: string) {
  const params = new URLSearchParams();
  if (target !== undefined) params.set("target", String(target));
  if (until) params.set("until", until);
  const query = params.toString();
  return get<AnnualPlan>(`${endpoints.finances.plan(userId)}${query ? `?${query}` : ""}`);
}

/* ===== Subscription audit ===== */

export async function fetchSubscriptions(userId: string) {
  return get<SubscriptionCandidate[]>(endpoints.finances.subscriptions(userId));
}

export async function confirmSubscription(
  userId: string,
  candidate: SubscriptionCandidate,
  /** The last date it runs, or null for ongoing (vision §13.9's "until when?"). */
  until: string | null = null,
): Promise<RecurringTransaction> {
  return post<RecurringTransaction>(endpoints.finances.confirmSubscription(userId), {
    transaction_ids: candidate.occurrences.map((occurrence) => occurrence.transaction_id),
    instruction: {
      ...candidate.suggested,
      recurrence: { ...candidate.suggested.recurrence, until },
    },
  });
}

/* ===== Sinking funds ===== */

export async function fetchSinkingFunds(userId: string, includeArchived = false) {
  const base = endpoints.finances.sinkingFunds(userId);
  return get<SinkingFund[]>(includeArchived ? `${base}?include_archived=true` : base);
}

export async function createSinkingFund(userId: string, payload: SinkingFundCreate) {
  return post<SinkingFund>(endpoints.finances.sinkingFunds(userId), payload);
}

export async function updateSinkingFund(
  userId: string,
  fundId: string,
  payload: SinkingFundUpdate
) {
  return patch<SinkingFund>(endpoints.finances.sinkingFund(userId, fundId), payload);
}

/** Set this month's money aside for real. Writes the transfer. */
export async function contributeToFund(
  userId: string,
  fundId: string,
  payload: ContributionRequest
) {
  return post<SinkingFund>(endpoints.finances.contribute(userId, fundId), payload);
}

/** Take a month's set-aside back, moving the money with it. */
export async function undoContribution(
  userId: string,
  fundId: string,
  contributionId: string
) {
  return del<SinkingFund>(
    endpoints.finances.contribution(userId, fundId, contributionId)
  );
}

/** Removes the fund and every transfer its contributions wrote. */
export async function deleteSinkingFund(userId: string, fundId: string) {
  return del<SinkingFund>(endpoints.finances.sinkingFund(userId, fundId));
}
