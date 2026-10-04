import { Recurrence } from "../calender/types";

/** Mirrors app/Jobs/schemas/job.py. */

/**
 * How a job pays.
 *
 * Three genuinely different arrangements rather than styling on one: each
 * answers "what should this have paid?" with a different question, and treating
 * them alike is what would make a salaried job look underpaid every time you
 * worked a long week.
 */
export enum JobKind {
  /** Hours times a rate. The hours are the pay. */
  HOURLY = "hourly",
  /** A fixed amount per pay period, however many hours it took. */
  SALARIED = "salaried",
  /** You invoice; the amount is whatever you billed. */
  CONTRACT = "contract",
}

export const JOB_KIND_LABELS: Record<JobKind, string> = {
  [JobKind.HOURLY]: "Hourly",
  [JobKind.SALARIED]: "Salaried",
  [JobKind.CONTRACT]: "Contract",
};

export interface Job {
  id: string;
  name: string;
  employer: string | null;
  kind: JobKind;
  /** Hourly jobs only. A shift may override it for one date. */
  hourly_rate: number | null;
  /** Salaried jobs only: what one pay period pays, regardless of hours. */
  period_amount: number | null;
  started_on: string | null;
  /** Null while the job is current. */
  ended_on: string | null;
  pay_starts_on: string | null;
  pay_schedule: Recurrence | null;
  archived: boolean;
  position: number;
  created_at: string | null;
  /** Read from the pay rule per request, never stored. */
  next_pay_on: string | null;
  is_current: boolean;
}

export interface JobCreate {
  name: string;
  employer: string | null;
  kind: JobKind;
  hourly_rate: number | null;
  period_amount: number | null;
  started_on: string | null;
  ended_on: string | null;
  pay_starts_on: string | null;
  pay_schedule: Recurrence | null;
  archived: boolean;
}

export type JobUpdate = Partial<JobCreate> & { position?: number };

/** One recurring block of a job's schedule. Same shape as a course's meeting. */
export interface ShiftMeeting {
  days: string[];
  start_time: string;
  end_time: string;
  location: string | null;
}

/** One shift on one date — the ordinary way part-time hours arrive. */
export interface ShiftCreate {
  on_date: string;
  start_time: string;
  end_time: string;
  location: string | null;
}

export interface ShiftScheduleCreate {
  meetings: ShiftMeeting[];
  starts_on: string | null;
  ends_on: string | null;
}

/**
 * One date a job's schedule falls on, with what is known about it.
 *
 * Materialised per request like every other occurrence, so it has no id of its
 * own: `(event_id, on_date)` is what identifies it.
 */
export interface ShiftOccurrence {
  event_id: string;
  job_id: string;
  job_name: string;
  on_date: string;
  title: string;
  scheduled_start: string | null;
  scheduled_end: string | null;
  location: string | null;
  scheduled_minutes: number;
  /** What was actually recorded, when it differs from the schedule. */
  worked_start: string | null;
  worked_end: string | null;
  /** Equal to the scheduled minutes until confirmed with different times. */
  counted_minutes: number;
  confirmed: boolean;
  /** False for a shift entered on its own; true for one a pattern produced.
   *  Only a one-off can be removed outright. */
  repeats: boolean;
  /**
   * A past shift nobody confirmed. Its hours are being assumed from the
   * schedule rather than known, and stay visible so a total can say how much of
   * itself is a guess.
   */
  assumed: boolean;
  tip_amount: number;
  tip_is_cash: boolean;
  /**
   * Whether a cash tip has actually reached the budget. False while it is held
   * for want of an account to go to (Settings -> Financial), and always false
   * for a tip paid on the cheque, which arrives inside the paycheque instead.
   */
  tip_in_ledger: boolean;
  rate_override: number | null;
  notes: string | null;
}

export interface ShiftRecordUpsert {
  worked_start: string | null;
  worked_end: string | null;
  confirmed: boolean;
  tip_amount: number;
  tip_is_cash: boolean;
  rate_override: number | null;
  notes: string | null;
}

/* ===== Paycheques ===== */

/** Mirrors app/Jobs/schemas/paycheque.py. */

export interface DeductionEntry {
  description: string;
  /** Positive. The sign is in the name. */
  amount: number;
}

export interface Deduction extends DeductionEntry {
  id: string;
}

export interface Paycheque {
  id: string;
  job_id: string;
  job_name: string;
  occurred_on: string;
  gross_amount: number;
  deductions: Deduction[];
  /** Gross less every deduction, computed by the API rather than stored. */
  net_amount: number;
  period_start: string | null;
  period_end: string | null;
  /** What the hours said it should be, frozen when the cheque was recorded. */
  expected_gross: number | null;
  /** Positive means the cheque was larger than expected. Null when nothing was expected. */
  variance: number | null;
  notes: string | null;
}

export interface PaychequeCreate {
  job_id: string;
  occurred_on: string;
  gross_amount: number;
  period_start: string | null;
  period_end: string | null;
  deductions: DeductionEntry[];
  /** Empty splits the net by each account's income share. */
  allocations: { account_id: string; amount: number }[];
  notes: string | null;
}

export type PaychequeUpdate = Partial<Omit<PaychequeCreate, "job_id">>;

export interface PaychequePreview {
  job_id: string;
  period_start: string;
  period_end: string;
  /** Null for a contract job: there is nothing to predict from hours. */
  expected_gross: number | null;
  shift_count: number;
  counted_minutes: number;
  /** How many of those shifts are assumed rather than confirmed. */
  assumed_count: number;
  /** Tips paid through payroll, already inside the gross. */
  on_cheque_tips: number;
}

/* ===== Earnings ===== */

/** Mirrors app/Jobs/schemas/earnings.py. */

export interface JobEarnings {
  job_id: string;
  job_name: string;
  kind: string;
  shift_count: number;
  counted_minutes: number;
  /** How many of those shifts are assumed rather than confirmed. */
  assumed_count: number;
  gross_earned: number;
  cash_tips: number;
  /**
   * From this job's cheques dated inside the window. Kept apart from
   * gross_earned for the same reason the window-level pair is: one is what the
   * hours say, the other what the bank saw, and a cheque arriving now usually
   * pays for work done before the window opened.
   */
  gross_paid: number;
  deducted: number;
  net_paid: number;
}

export interface EarningsWindow {
  label: string;
  starts_on: string;
  ends_on: string;
  counted_minutes: number;
  /** What the hours say. A prediction. */
  gross_earned: number;
  cash_tips: number;
  /** What cheques actually paid. Kept apart from earned on purpose. */
  gross_paid: number;
  deducted: number;
  net_paid: number;
  per_job: JobEarnings[];
}

export interface EffectiveRate {
  /** Null before anything has been paid, rather than a zero that reads as unpaid work. */
  net_per_hour: number | null;
  gross_per_hour: number | null;
  deduction_percent: number | null;
  paid_minutes: number;
}

export interface UpcomingPay {
  job_id: string;
  job_name: string;
  unpaid_minutes: number;
  /** Null for a contract job, which predicts nothing from hours. */
  unpaid_estimate: number | null;
  next_pay_on: string | null;
}

export interface HoursAgainstClasses {
  starts_on: string;
  ends_on: string;
  work_minutes: number;
  class_minutes: number;
  task_minutes: number;
}

export interface EarningsSummary {
  week: EarningsWindow;
  month: EarningsWindow;
  term: EarningsWindow | null;
  effective_rate: EffectiveRate;
  upcoming: UpcomingPay[];
  this_week: HoursAgainstClasses | null;
}
