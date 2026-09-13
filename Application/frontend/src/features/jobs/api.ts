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
} from "./types";

export async function fetchJobs(userId: string, includeArchived = false) {
  const base = endpoints.jobs.list(userId);
  return get<Job[]>(includeArchived ? `${base}?include_archived=true` : base);
}

export async function createJob(userId: string, payload: JobCreate) {
  return post<Job>(endpoints.jobs.list(userId), payload);
}

export async function updateJob(userId: string, jobId: string, payload: JobUpdate) {
  return patch<Job>(endpoints.jobs.detail(userId, jobId), payload);
}

/** Removes the job and the calendar blocks it put up. Ending one is `ended_on`. */
export async function deleteJob(userId: string, jobId: string) {
  return del<Job>(endpoints.jobs.detail(userId, jobId));
}

/** Replaces the job's recurring shifts with the pattern given. */
export async function setShiftSchedule(
  userId: string,
  jobId: string,
  payload: ShiftScheduleCreate
) {
  return put<string[]>(endpoints.jobs.schedule(userId, jobId), payload);
}

export async function fetchShifts(userId: string, start: string, end: string) {
  return get<ShiftOccurrence[]>(
    `${endpoints.jobs.shifts(userId)}?start=${start}&end=${end}`
  );
}

/**
 * Confirm what was actually worked on one date.
 *
 * A PUT because `(event_id, on_date)` names the thing being written: confirming
 * the same Friday twice must leave one answer rather than two.
 */
export async function recordShift(
  userId: string,
  eventId: string,
  onDate: string,
  payload: ShiftRecordUpsert
) {
  return put<unknown>(endpoints.jobs.shiftRecord(userId, eventId, onDate), payload);
}

/* ===== Paycheques ===== */

export async function fetchPaycheques(userId: string, jobId?: string) {
  const base = endpoints.jobs.paycheques(userId);
  return get<Paycheque[]>(jobId ? `${base}?job_id=${jobId}` : base);
}

/** What the shifts in a period say the cheque should come to. */
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

export async function recordPaycheque(userId: string, payload: PaychequeCreate) {
  return post<Paycheque>(endpoints.jobs.paycheques(userId), payload);
}

export async function updatePaycheque(
  userId: string,
  paychequeId: string,
  payload: PaychequeUpdate
) {
  return patch<Paycheque>(endpoints.jobs.paycheque(userId, paychequeId), payload);
}

/** Removes the cheque and the ledger rows it wrote. */
export async function deletePaycheque(userId: string, paychequeId: string) {
  return del<Paycheque>(endpoints.jobs.paycheque(userId, paychequeId));
}

/** Hours and money over a week, a month and the term, in one call. */
export async function fetchEarnings(userId: string) {
  return get<EarningsSummary>(endpoints.jobs.earnings(userId));
}

/**
 * Add one shift on one date.
 *
 * The ordinary path: part-time hours are rarely the same twice, so a shift is
 * entered as it is given to you. A weekly pattern is the exception, and goes
 * through setShiftSchedule instead.
 */
export async function addShift(userId: string, jobId: string, payload: ShiftCreate) {
  return post<string>(endpoints.jobs.addShift(userId, jobId), payload);
}

/** Remove a one-off shift. A date from a pattern is cancelled on the calendar. */
export async function deleteShift(userId: string, eventId: string) {
  return del<string>(endpoints.jobs.shift(userId, eventId));
}
