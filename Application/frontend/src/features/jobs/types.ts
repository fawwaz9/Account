import { Recurrence, Weekday } from "../calender/types";

/** Jobs, shifts, paycheques, earnings and the tax packet; mirrors app/Jobs/schemas/job.py. */

/** How a job pays; each kind answers "what should this have paid?" its own way. */
export enum JobKind {
  /** Hours times a rate. */
  HOURLY = "hourly",
  /** A set amount per pay period, however many hours. */
  SALARIED = "salaried",
  /** Invoiced; pays whatever was billed. */
  CONTRACT = "contract",
}

/** Display label per job kind. */
export const JOB_KIND_LABELS: Record<JobKind, string> = {
  [JobKind.HOURLY]: "Hourly",
  [JobKind.SALARIED]: "Salaried",
  [JobKind.CONTRACT]: "Contract",
};

/** A job with its pay rule. */
export interface Job {
  id: string;
  name: string;
  employer: string | null;
  kind: JobKind;
  /** Hourly jobs only; a shift may override it for one date. */
  hourly_rate: number | null;
  /** Salaried jobs only: one pay period's pay, regardless of hours. */
  period_amount: number | null;
  started_on: string | null;
  /** Null while the job is current. */
  ended_on: string | null;
  /** First pay date; required with either kind of pay rule. */
  pay_starts_on: string | null;
  /** Repeat rule for pay dates; never with `pay_days`. */
  pay_schedule: Recurrence | null;
  /** Pay on set days of the month instead of `pay_schedule`; never both. */
  pay_days: PayDays | null;
  archived: boolean;
  position: number;
  created_at: string | null;
  /** Next pay date, read from the pay rule per request, never stored. */
  next_pay_on: string | null;
  is_current: boolean;
}

/** Body to create a job. */
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
  pay_days: PayDays | null;
  archived: boolean;
}

/** Where a pay date landing on a weekend moves. */
export type WeekendRule = "previous" | "next" | "keep";

/** An Nth weekday of the month: n = 2 is the 2nd, n = -1 the last. */
export interface NthWeekday {
  n: 1 | 2 | 3 | 4 | -1;
  day: Weekday;
}

/** Pay on set days of the month: dates, the last day, or Nth weekdays. */
export interface PayDays {
  /** Days of the month; one the month lacks pays on its last day. */
  dates: number[];
  /** Also pay on the month's last day; may go with `dates`. */
  last_day: boolean;
  /** Nth weekdays, at most four; never with `dates` or `last_day`. */
  nth_weekdays: NthWeekday[];
  weekend: WeekendRule;
  /** Last scheduled pay date, inclusive; null for no end. */
  until: string | null;
}

/** Partial job edit, plus its list position. */
export type JobUpdate = Partial<JobCreate> & { position?: number };

/** One weekly slot of a job's schedule, shaped like a course meeting. */
export interface ShiftMeeting {
  /** Weekday codes, "MO" to "SU". */
  days: string[];
  start_time: string;
  end_time: string;
  location: string | null;
}

/** Body for one shift on one date. */
export interface ShiftCreate {
  on_date: string;
  start_time: string;
  end_time: string;
  location: string | null;
}

/** Body to set a job's repeating schedule. */
export interface ShiftScheduleCreate {
  meetings: ShiftMeeting[];
  starts_on: string | null;
  ends_on: string | null;
}

/**
 * One date a job's schedule falls on, with what was recorded.
 * Expanded per request with no row of its own: the event id and date identify it.
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
  /** Recorded start, when it differs from the schedule. */
  worked_start: string | null;
  worked_end: string | null;
  /** The scheduled minutes until confirmed with different times. */
  counted_minutes: number;
  confirmed: boolean;
  /** True when a pattern produced it; only a one-off can be removed outright. */
  repeats: boolean;
  /** A past shift nobody confirmed, counted at its scheduled hours. */
  assumed: boolean;
  tip_amount: number;
  tip_is_cash: boolean;
  /** A cash tip already filed to the budget; false while held, and for cheque tips. */
  tip_in_ledger: boolean;
  /** Rate for this date only; null uses the job's. */
  rate_override: number | null;
  notes: string | null;
}

/** Body to record one shift date's actuals. */
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

/** One deduction line on a paycheque. */
export interface DeductionEntry {
  description: string;
  /** Positive; the sign is in the name. */
  amount: number;
}

/** A stored deduction line. */
export interface Deduction extends DeductionEntry {
  id: string;
}

/** A recorded paycheque; only its net reaches the ledger. */
export interface Paycheque {
  id: string;
  job_id: string;
  job_name: string;
  occurred_on: string;
  gross_amount: number;
  deductions: Deduction[];
  /** Gross less every deduction, computed by the API. */
  net_amount: number;
  period_start: string | null;
  period_end: string | null;
  /** What the hours said it should be, frozen when recorded. */
  expected_gross: number | null;
  /** Gross less expected; positive is a larger cheque, null when nothing was expected. */
  variance: number | null;
  notes: string | null;
}

/** Body to record a paycheque. */
export interface PaychequeCreate {
  job_id: string;
  occurred_on: string;
  gross_amount: number;
  period_start: string | null;
  period_end: string | null;
  deductions: DeductionEntry[];
  /** Explicit split of the net; empty splits by income share. */
  allocations: { account_id: string; amount: number }[];
  notes: string | null;
}

/** Partial paycheque edit; the job cannot change. */
export type PaychequeUpdate = Partial<Omit<PaychequeCreate, "job_id">>;

/** What a pay period's shifts predict, before the cheque is recorded. */
export interface PaychequePreview {
  job_id: string;
  period_start: string;
  period_end: string;
  /** Null for a contract job: hours predict nothing. */
  expected_gross: number | null;
  shift_count: number;
  counted_minutes: number;
  /** How many of those shifts are assumed, not confirmed. */
  assumed_count: number;
  /** Tips paid through payroll, already inside the gross. */
  on_cheque_tips: number;
}

/* ===== Earnings ===== */

/** Mirrors app/Jobs/schemas/earnings.py. */

/** One job's earned and paid figures in a window. */
export interface JobEarnings {
  job_id: string;
  job_name: string;
  /** "hourly", "salaried" or "contract". */
  kind: string;
  shift_count: number;
  counted_minutes: number;
  /** Shifts counted at their schedule because nobody confirmed them. */
  assumed_count: number;
  /** Predicted from the shifts; for a salaried job, the periods in the window. */
  gross_earned: number;
  cash_tips: number;
  /** Gross of this job's cheques dated in the window; never added to earned. */
  gross_paid: number;
  deducted: number;
  net_paid: number;
}

/** Earned against paid over one window: past week, this month or this term. */
export interface EarningsWindow {
  label: string;
  starts_on: string;
  /** Inclusive, and never after today. */
  ends_on: string;
  counted_minutes: number;
  /** Predicted from the shifts worked. */
  gross_earned: number;
  cash_tips: number;
  /** What cheques dated in the window paid; kept apart from earned. */
  gross_paid: number;
  deducted: number;
  net_paid: number;
  per_job: JobEarnings[];
}

/** Pay per hour actually worked, over the paid periods. */
export interface EffectiveRate {
  /** Null before anything is paid, rather than a zero. */
  net_per_hour: number | null;
  gross_per_hour: number | null;
  /** Deductions as a percent of gross. */
  deduction_percent: number | null;
  paid_minutes: number;
}

/** Work since the latest cheque, and what it should pay. */
export interface UpcomingPay {
  job_id: string;
  job_name: string;
  /** Shift minutes since the last cheque's period ended. */
  unpaid_minutes: number;
  /** Null for a contract job, which predicts nothing from hours. */
  unpaid_estimate: number | null;
  next_pay_on: string | null;
}

/** This week's minutes of work against classes and tasks. */
export interface HoursAgainstClasses {
  starts_on: string;
  ends_on: string;
  work_minutes: number;
  class_minutes: number;
  task_minutes: number;
}

/** The Jobs page's earnings: three windows, the effective rate and pay to come. */
export interface EarningsSummary {
  week: EarningsWindow;
  month: EarningsWindow;
  term: EarningsWindow | null;
  effective_rate: EffectiveRate;
  upcoming: UpcomingPay[];
  this_week: HoursAgainstClasses | null;
}

/** One line of a cheque check's arithmetic, with the rule it came from. */
export interface PayLine {
  label: string;
  hours: number | null;
  rate: number | null;
  amount: number;
  rule: string | null;
}

/** A cheque checked against its shifts under BC pay rules. */
export interface PayCheck {
  paycheque_id: string;
  status: "as_expected" | "as_expected_with_vacation" | "short" | "over" | "unclear" | "cannot_check";
  summary: string;
  actual_gross: number;
  expected: number | null;
  expected_with_vacation: number | null;
  vacation_percent: number | null;
  difference: number | null;
  lines: PayLine[];
  notes: string[];
}

/**
 * A shift against an exam.
 * `overlap` shares time with it; `crowds` ends less than the buffer before it starts.
 */
export interface ShiftConflict {
  kind: "overlap" | "crowds";
  shift_event_id: string;
  shift_on: string;
  shift_start: string | null;
  /** Local end; earlier than the start for an overnight shift. */
  shift_end: string | null;
  job_id: string | null;
  job_name: string | null;
  exam_event_id: string;
  exam_title: string;
  exam_kind: string;
  exam_on: string;
  /** Null while unknown, taken as 08:00. */
  exam_start: string | null;
  course_code: string | null;
  /** Hours from the shift's end to the exam's start, 1 dp. */
  hours_between: number;
}

/** Every shift-exam conflict, with the buffer used. */
export interface ShiftConflicts {
  /** The exam buffer from Settings; 0 flags only overlaps. */
  buffer_hours: number;
  conflicts: ShiftConflict[];
}

/** One deduction total by kind, for the tax packet. */
export interface DeductionLine {
  kind: "income_tax" | "cpp" | "ei" | "other";
  label: string;
  amount: number;
}

/** One job's year: cheques, gross, deductions by kind, net and tips. */
export interface EmployerYear {
  job_name: string;
  employer: string | null;
  paycheques: number;
  gross: number;
  deductions: DeductionLine[];
  net: number;
  cash_tips: number;
  /** Tips paid through payroll, which may already sit inside `gross`. */
  other_tips: number;
}

/** A year's employment income from recorded cheques, never a T4, beside tuition paid. */
export interface TaxPacket {
  /** Calendar year; a cheque counts in the year it arrived. */
  year: number;
  employers: EmployerYear[];
  gross: number;
  income_tax: number;
  cpp: number;
  ei: number;
  other_deductions: number;
  net: number;
  cash_tips: number;
  tuition_paid: number;
}
