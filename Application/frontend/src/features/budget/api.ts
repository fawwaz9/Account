import { del, get, patch, post, put } from "../../services/apiClient";
import { clearApiCache } from "../../services/apiCache";
import { endpoints } from "../../services/endpoints";
import {
  ContributionRequest,
  SinkingFund,
  SinkingFundCreate,
  SinkingFundUpdate,
  SafeToSpend,
  CashFlowForecast,
  AnnualPlan,
  PlanReview,
  SavedPlan,
  ImportMapping,
  ImportPreview,
  ImportSummary,
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

/** Fetch net worth, computed on the server so the budget page and dashboard agree. */
export async function fetchNetWorth(userId: string): Promise<NetWorth> {
  return get<NetWorth>(endpoints.finances.netWorth(userId));
}

/** Fetch every account with its balance. */
export async function fetchAccounts(userId: string): Promise<Account[]> {
  return get<Account[]>(endpoints.finances.accounts(userId));
}

/** Create an account. */
export async function createAccount(userId: string, payload: AccountCreate) {
  return post<Account>(endpoints.finances.accounts(userId), payload);
}

/** Edit an account's fields. */
export async function updateAccount(
  userId: string,
  accountId: string,
  payload: Partial<AccountCreate>
) {
  return patch<Account>(endpoints.finances.account(userId, accountId), payload);
}

/** Delete an account. */
export async function deleteAccount(userId: string, accountId: string) {
  return del<Account>(endpoints.finances.account(userId, accountId));
}

/**
 * Record an investment's market value for a month; an upsert.
 * Returns the whole account, so the card updates without a second fetch.
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

/** Forget one month's investment reading; the month is always given. */
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
 * Fetch transactions, optionally one account's and within inclusive dates.
 * The server returns at most 100, newest first: window it there, never trim them here.
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

/** One account's month: daily flow, totals, categories and target. */
export async function fetchAccountActivity(
  userId: string,
  accountId: string,
  month: string
) {
  const base = endpoints.finances.accountActivity(userId, accountId);
  return get<AccountActivity>(`${base}?month=${month}`);
}

/** Record income or an expense. */
export async function createTransaction(userId: string, payload: TransactionCreate) {
  return post<Transaction>(endpoints.finances.transactions(userId), payload);
}

/** Record a transfer; returns both halves. */
export async function createTransfer(userId: string, payload: TransferCreate) {
  return post<Transaction[]>(endpoints.finances.transfers(userId), payload);
}

/** Edit a transaction's amount, description, date or category. */
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
 * Delete a transaction: `scope` row takes this one, group every row sharing its group.
 * A transfer always goes whole.
 */
export async function deleteTransaction(
  userId: string,
  transactionId: string,
  scope: "row" | "group" = "group"
) {
  const base = endpoints.finances.transaction(userId, transactionId);
  return del<Transaction>(`${base}?scope=${scope}`);
}

/** Fetch the spending categories. */
export async function fetchCategories(userId: string) {
  return get<SpendCategory[]>(endpoints.finances.categories(userId));
}

/** Create a category. */
export async function createCategory(userId: string, name: string) {
  return post<SpendCategory>(endpoints.finances.categories(userId), {
    name,
    archived: false,
    position: 0,
  });
}

/** Rename, archive or reorder a category. */
export async function updateCategory(
  userId: string,
  categoryId: string,
  payload: { name?: string; archived?: boolean; position?: number }
) {
  return patch<SpendCategory>(endpoints.finances.category(userId, categoryId), payload);
}

/** Delete a category; its expenses become uncategorised. */
export async function deleteCategory(userId: string, categoryId: string) {
  return del<SpendCategory>(endpoints.finances.category(userId, categoryId));
}

/** Set an account's planned spend for a month, replacing any earlier figure. */
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
 * Set an account's limit for one category, or null to clear it.
 * Null removes the limit; 0 is a real limit that closes the category.
 */
export async function setAccountCategoryLimit(
  userId: string,
  accountId: string,
  categoryId: string,
  limitAmount: number | null,
  /** Null sets the standing limit; a month sets only that month's override. */
  month: string | null = null
) {
  return put<unknown>(endpoints.finances.accountCategoryLimits(userId), {
    account_id: accountId,
    category_id: categoryId,
    month,
    limit_amount: limitAmount,
  });
}

/** Fetch a month's budget summary across accounts. */
export async function fetchBudgetSummary(userId: string, month: string) {
  return get<BudgetSummary>(`${endpoints.finances.budgetSummary(userId)}?month=${month}`);
}

/** How a deposit would split by income share, using the server's rounding rule. */
export async function previewDeposit(userId: string, amount: number) {
  return get<DepositPreview>(
    `${endpoints.finances.depositPreview(userId)}?amount=${amount}`
  );
}

/** Record a deposit; returns one income row per account. */
export async function recordDeposit(userId: string, payload: DepositCreate) {
  return post<Transaction[]>(endpoints.finances.deposits(userId), payload);
}

/* ===== Standing instructions ===== */

/** Fetch standing instructions, inactive ones included by default. */
export async function fetchRecurring(userId: string, includeInactive = true) {
  const base = endpoints.finances.recurring(userId);
  return get<RecurringTransaction[]>(`${base}?include_inactive=${includeInactive}`);
}

/** Create a standing instruction. */
export async function createRecurring(userId: string, payload: RecurringCreate) {
  return post<RecurringTransaction>(endpoints.finances.recurring(userId), payload);
}

/** Edit a standing instruction. */
export async function updateRecurring(
  userId: string,
  ruleId: string,
  payload: RecurringUpdate
) {
  return patch<RecurringTransaction>(endpoints.finances.recurringRule(userId, ruleId), payload);
}

/** Delete a standing instruction; payments it already made stay. */
export async function deleteRecurring(userId: string, ruleId: string) {
  return del<RecurringTransaction>(endpoints.finances.recurringRule(userId, ruleId));
}

/**
 * Write every payment now owed; idempotent, so it runs on every load.
 * Keeps the GET cache unless it wrote something.
 */
export async function runRecurring(userId: string) {
  // Run on every load and usually writes nothing, so it clears the GET cache
  // only when it wrote something (apiCache.ts).
  const run = await post<RecurringRun>(endpoints.finances.recurringRun(userId), {}, { keepCache: true });
  if (run.created > 0) clearApiCache();
  return run;
}

/** Standing-instruction payments due in a window: projections, never rows. */
export async function fetchUpcoming(userId: string, start: string, end: string) {
  const base = endpoints.finances.recurringUpcoming(userId);
  return get<UpcomingCharge[]>(`${base}?start=${start}&end=${end}`);
}

/** Skip one payment of a standing instruction without ending it. */
export async function skipRecurring(userId: string, ruleId: string, onDate: string) {
  return post<RecurringTransaction>(
    `${endpoints.finances.recurringSkip(userId, ruleId)}?on_date=${onDate}`,
    {}
  );
}

/** Ask the server which course a line of text names. */
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

/** Record a tuition payment and its one ledger row. */
export async function recordTuition(userId: string, data: TuitionCreate) {
  return post(endpoints.finances.tuition(userId), data);
}

/** What a course cost: its gross tuition share plus anything bought for it. */
export async function fetchCourseCost(userId: string, courseId: string) {
  return get<CourseCost>(endpoints.finances.courseCost(userId, courseId));
}

/** Fetch one tuition payment. */
export async function fetchTuitionPayment(userId: string, paymentId: string) {
  return get<TuitionPayment>(endpoints.finances.tuitionPayment(userId, paymentId));
}

/** Correct a tuition payment; its ledger row moves with it. */
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

/** Delete a tuition payment and the ledger row it owns. */
export async function deleteTuition(userId: string, paymentId: string) {
  return del(endpoints.finances.tuitionPayment(userId, paymentId));
}

/** What the current term has cost, over the term's own dates. */
export async function fetchTermBudget(userId: string) {
  return get<TermBudget>(endpoints.finances.termBudget(userId));
}

/** Safe-to-spend until the next payday: `safe_now` is the answer, `safe_soon` context. */
export async function fetchSafeToSpend(userId: string) {
  return get<SafeToSpend>(endpoints.finances.safeToSpend(userId));
}

/** Forecast the spending accounts to the end of the term. */
export async function fetchForecast(userId: string) {
  return get<CashFlowForecast>(endpoints.finances.forecast(userId));
}

/** Year plan; with a target, the weekly hours it takes. */
export async function fetchPlan(userId: string, target?: number, until?: string) {
  const params = new URLSearchParams();
  if (target !== undefined) params.set("target", String(target));
  if (until) params.set("until", until);
  const query = params.toString();
  return get<AnnualPlan>(`${endpoints.finances.plan(userId)}${query ? `?${query}` : ""}`);
}

/** Save the plan as it stands, as a new copy, to compare months against. */
export async function savePlan(userId: string) {
  return post<SavedPlan>(endpoints.finances.planSaved(userId), {});
}

/** Each finished month against the plan saved before it began. */
export async function fetchPlanReview(userId: string) {
  return get<PlanReview>(endpoints.finances.planReview(userId));
}

/* ===== CSV import ===== */

/** Preview a CSV import, duplicates flagged; writes nothing. */
export async function previewImport(
  userId: string, accountId: string, csvText: string, mapping: ImportMapping | null = null,
) {
  return post<ImportPreview>(endpoints.finances.importPreview(userId), {
    account_id: accountId, csv_text: csvText, mapping,
  });
}

/** Write the chosen lines; the server re-reads them from the same text and mapping. */
export async function commitImport(
  userId: string, accountId: string, csvText: string, mapping: ImportMapping, lines: number[],
  filename: string | null, categories: Record<number, string | null> = {},
) {
  return post<ImportSummary>(endpoints.finances.imports(userId), {
    account_id: accountId, csv_text: csvText, mapping, lines, filename, categories,
  });
}

/** Fetch past imports. */
export async function fetchImports(userId: string) {
  return get<ImportSummary[]>(endpoints.finances.imports(userId));
}

/** Undo an import, removing every row it wrote that remains. */
export async function deleteImport(userId: string, importId: string) {
  return del<{ removed: number }>(endpoints.finances.importOne(userId, importId));
}

/* ===== Subscription audit ===== */

/** Fetch repeating charges spotted in the ledger. */
export async function fetchSubscriptions(userId: string) {
  return get<SubscriptionCandidate[]>(endpoints.finances.subscriptions(userId));
}

/** Confirm a spotted subscription as a standing instruction, passing its past charges. */
export async function confirmSubscription(
  userId: string,
  candidate: SubscriptionCandidate,
  /** Last date it runs, or null for ongoing. */
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

/** Fetch sinking funds; archived ones only on request. */
export async function fetchSinkingFunds(userId: string, includeArchived = false) {
  const base = endpoints.finances.sinkingFunds(userId);
  return get<SinkingFund[]>(includeArchived ? `${base}?include_archived=true` : base);
}

/** Create a sinking fund. */
export async function createSinkingFund(userId: string, payload: SinkingFundCreate) {
  return post<SinkingFund>(endpoints.finances.sinkingFunds(userId), payload);
}

/** Edit a sinking fund. */
export async function updateSinkingFund(
  userId: string,
  fundId: string,
  payload: SinkingFundUpdate
) {
  return patch<SinkingFund>(endpoints.finances.sinkingFund(userId, fundId), payload);
}

/** Transfer this month's contribution into a fund. */
export async function contributeToFund(
  userId: string,
  fundId: string,
  payload: ContributionRequest
) {
  return post<SinkingFund>(endpoints.finances.contribute(userId, fundId), payload);
}

/** Undo a month's contribution, deleting its transfer. */
export async function undoContribution(
  userId: string,
  fundId: string,
  contributionId: string
) {
  return del<SinkingFund>(
    endpoints.finances.contribution(userId, fundId, contributionId)
  );
}

/** Delete a fund and every transfer its contributions wrote. */
export async function deleteSinkingFund(userId: string, fundId: string) {
  return del<SinkingFund>(endpoints.finances.sinkingFund(userId, fundId));
}
