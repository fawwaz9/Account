import { del, get, patch, post, put } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import {
  ShiftCreate,
  EarningsSummary,
  Job,
  JobCreate,
  JobUpdate,
  Paycheque,
  PaychequeCreate,
  PaychequePreview,
  PaychequeUpdate,
  ShiftOccurrence,
  ShiftRecordUpsert,
  ShiftScheduleCreate,
  PayCheck,
  ShiftConflicts,
  TaxPacket,
  Client,
  Invoice,
  InvoiceCreate,
  PaidCreate,
  SelfEmployment,
} from "./types";

/** Fetch jobs; archived ones only on request. */
export async function fetchJobs(userId: string, includeArchived = false) {
  const base = endpoints.jobs.list(userId);
  return get<Job[]>(includeArchived ? `${base}?include_archived=true` : base);
}

/** Create a job. */
export async function createJob(userId: string, payload: JobCreate) {
  return post<Job>(endpoints.jobs.list(userId), payload);
}

/** Edit a job. */
export async function updateJob(userId: string, jobId: string, payload: JobUpdate) {
  return patch<Job>(endpoints.jobs.detail(userId, jobId), payload);
}

/** Delete a job with its shifts and paycheques; ledger rows stay. Ending a job is `ended_on`. */
export async function deleteJob(userId: string, jobId: string) {
  return del<Job>(endpoints.jobs.detail(userId, jobId));
}

/** Replace the job's repeating shifts with the pattern given. */
export async function setShiftSchedule(
  userId: string,
  jobId: string,
  payload: ShiftScheduleCreate
) {
  return put<string[]>(endpoints.jobs.schedule(userId, jobId), payload);
}

/** Shift occurrences between two dates, inclusive. */
export async function fetchShifts(userId: string, start: string, end: string) {
  return get<ShiftOccurrence[]>(
    `${endpoints.jobs.shifts(userId)}?start=${start}&end=${end}`
  );
}

/** Record one shift date's actuals; a PUT, so confirming twice leaves one answer. */
export async function recordShift(
  userId: string,
  eventId: string,
  onDate: string,
  payload: ShiftRecordUpsert
) {
  return put<unknown>(endpoints.jobs.shiftRecord(userId, eventId, onDate), payload);
}

/* ===== Paycheques ===== */

/** Fetch paycheques, optionally one job's. */
export async function fetchPaycheques(userId: string, jobId?: string) {
  const base = endpoints.jobs.paycheques(userId);
  return get<Paycheque[]>(jobId ? `${base}?job_id=${jobId}` : base);
}

/** What a period's shifts say the cheque should come to. */
export async function previewPaycheque(
  userId: string,
  jobId: string,
  periodStart: string,
  periodEnd: string
) {
  return get<PaychequePreview>(
    `${endpoints.jobs.paychequePreview(userId)}` +
      `?job_id=${jobId}&period_start=${periodStart}&period_end=${periodEnd}`
  );
}

/** Record a paycheque; its net is deposited by income share or as split. */
export async function recordPaycheque(userId: string, payload: PaychequeCreate) {
  return post<Paycheque>(endpoints.jobs.paycheques(userId), payload);
}

/** Edit a paycheque. */
export async function updatePaycheque(
  userId: string,
  paychequeId: string,
  payload: PaychequeUpdate
) {
  return patch<Paycheque>(endpoints.jobs.paycheque(userId, paychequeId), payload);
}

/** Delete a paycheque and the ledger rows it wrote. */
export async function deletePaycheque(userId: string, paychequeId: string) {
  return del<Paycheque>(endpoints.jobs.paycheque(userId, paychequeId));
}

/** Check a cheque against its shifts, BC overtime and vacation pay applied. */
export async function checkPaycheque(userId: string, paychequeId: string) {
  return get<PayCheck>(endpoints.jobs.paychequeCheck(userId, paychequeId));
}

/** Hours and money over a week, a month and the term, in one call. */
export async function fetchEarnings(userId: string) {
  return get<EarningsSummary>(endpoints.jobs.earnings(userId));
}

/** Add one shift on one date, the usual way hours arrive; patterns use `setShiftSchedule`. */
export async function addShift(userId: string, jobId: string, payload: ShiftCreate) {
  return post<string>(endpoints.jobs.addShift(userId, jobId), payload);
}

/** Delete a one-off shift; a pattern's date is cancelled on the calendar instead. */
export async function deleteShift(userId: string, eventId: string) {
  return del<string>(endpoints.jobs.shift(userId, eventId));
}

/** Answer to choosing the cash-tip account. */
export interface CashTipAccountResult {
  account_id: string | null;
  /** Held cash tips this choice filed into the account. */
  filed: number;
}

/** Choose the account cash tips go to, or null to hold them; choosing files every held tip. */
export async function chooseCashTipAccount(userId: string, accountId: string | null) {
  return put<CashTipAccountResult>(endpoints.jobs.cashTipAccount(userId), { account_id: accountId });
}


/** Shifts that run into, or crowd, an exam. */
export async function fetchShiftConflicts(userId: string, start?: string, end?: string) {
  const query = new URLSearchParams();
  if (start) query.set("start", start);
  if (end) query.set("end", end);
  const suffix = query.toString() ? `?${query}` : "";
  return get<ShiftConflicts>(`jobs/${userId}/shift-conflicts${suffix}`);
}

/** A calendar year's employment income, from recorded paycheques only. */
export async function fetchTaxPacket(userId: string, calendarYear: number) {
  return get<TaxPacket>(`jobs/${userId}/tax-packet?calendar_year=${calendarYear}`);
}

/** Phase 4 item 15: the caller's clients with their invoice totals. */
export async function fetchClients(userId: string) {
  return get<Client[]>(`jobs/${userId}/clients`);
}

/** Add a client. */
export async function createClient(userId: string, name: string) {
  return post<Client>(`jobs/${userId}/clients`, { name });
}

/** Rename or archive a client. */
export async function updateClient(userId: string, clientId: string, payload: { name?: string; archived?: boolean }) {
  return patch<Client>(`jobs/${userId}/clients/${clientId}`, payload);
}

/** Delete a client with no invoices. */
export async function deleteClient(userId: string, clientId: string) {
  return del<void>(`jobs/${userId}/clients/${clientId}`);
}

/** The caller's invoices, latest issued first. */
export async function fetchInvoices(userId: string) {
  return get<Invoice[]>(`jobs/${userId}/invoices`);
}

/** Record an invoice. */
export async function createInvoice(userId: string, payload: InvoiceCreate) {
  return post<Invoice>(`jobs/${userId}/invoices`, payload);
}

/** Correct an invoice. */
export async function updateInvoice(userId: string, invoiceId: string, payload: Partial<InvoiceCreate>) {
  return patch<Invoice>(`jobs/${userId}/invoices/${invoiceId}`, payload);
}

/** Delete an invoice and any deposit its payment wrote. */
export async function deleteInvoice(userId: string, invoiceId: string) {
  return del<void>(`jobs/${userId}/invoices/${invoiceId}`);
}

/** Mark an invoice paid. */
export async function markInvoicePaid(userId: string, invoiceId: string, payload: PaidCreate) {
  return post<Invoice>(`jobs/${userId}/invoices/${invoiceId}/paid`, payload);
}

/** Mark an invoice unpaid again; its deposit goes. */
export async function markInvoiceUnpaid(userId: string, invoiceId: string) {
  return del<Invoice>(`jobs/${userId}/invoices/${invoiceId}/paid`);
}

/** A year of self-employment and the CRA rules read against it. */
export async function fetchSelfEmployment(userId: string, year?: number) {
  return get<SelfEmployment>(`jobs/${userId}/self-employment${year ? `?year=${year}` : ""}`);
}
