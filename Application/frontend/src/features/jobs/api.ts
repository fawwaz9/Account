import { del, get, patch, post, put } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import {
  Job,
  JobCreate,
  JobUpdate,
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
