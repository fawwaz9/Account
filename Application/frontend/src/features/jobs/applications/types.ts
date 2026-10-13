/** Mirrors app/Jobs/schemas/application.py (Phase 3 item 1, D2-D5). */

export type ApplicationStatus =
  | "applied" | "screening" | "interview" | "offer" | "accepted" | "rejected" | "no_reply" | "withdrawn";

export type OfferPeriod = "hourly" | "monthly" | "yearly";

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: "Applied",
  screening: "Screening",
  interview: "Interview",
  offer: "Offer",
  accepted: "Accepted",
  rejected: "Rejected",
  no_reply: "No reply",
  withdrawn: "Withdrawn",
};

/** The statuses a step can record: everything after "applied", which is the first. */
export const STEP_STATUSES: ApplicationStatus[] = [
  "screening", "interview", "offer", "accepted", "rejected", "no_reply", "withdrawn",
];

/** Still in play: waiting on them, or an offer waiting on you. */
export const OPEN_STATUSES: ApplicationStatus[] = ["applied", "screening", "interview", "offer"];

export interface Step {
  id: string;
  status: ApplicationStatus;
  on_date: string;
  note: string | null;
}

export interface Application {
  id: string;
  company: string;
  role: string;
  applied_on: string;
  source: string | null;
  link: string | null;
  location: string | null;
  notes: string | null;
  status: ApplicationStatus;
  deadline: string | null;
  follow_up_on: string | null;
  /** Private to you (D5). */
  offer_amount: number | null;
  offer_period: OfferPeriod | null;
  steps: Step[];
  last_step_on: string;
  /** Quiet for 30 days while still waiting on them: "no reply yet?" (D3). */
  quiet: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApplicationInput {
  company: string;
  role: string;
  applied_on: string;
  source: string | null;
  link: string | null;
  location: string | null;
  notes: string | null;
  deadline: string | null;
  follow_up_on: string | null;
  offer_amount: number | null;
  offer_period: OfferPeriod | null;
}

export interface StepInput {
  status: ApplicationStatus;
  on_date: string;
  note: string | null;
}

/** One band of the Sankey. A stage is a status, or "waiting" for one still open. */
export interface Flow {
  source: string;
  target: string;
  count: number;
}

export interface ApplicationStats {
  total: number;
  open: number;
  replied: number;
  reply_rate: number | null;
  median_days_to_reply: number | null;
  interviews: number;
  offers: number;
  accepted: number;
  by_status: Record<string, number>;
  flows: Flow[];
}
