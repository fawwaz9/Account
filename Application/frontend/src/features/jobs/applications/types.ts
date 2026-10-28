/** Job applications, their steps and seasons; mirrors app/Jobs/schemas/application.py. */

/** Where an application stands; each dated step moves it. */
export type ApplicationStatus =
  | "applied" | "screening" | "interview" | "offer" | "accepted" | "rejected" | "no_reply" | "withdrawn";

/** How often an offer's pay is paid. */
export type OfferPeriod = "hourly" | "monthly" | "yearly";

/** Display label per status. */
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

/** Statuses a step can record: all but applied, which is always the first step. */
export const STEP_STATUSES: ApplicationStatus[] = [
  "screening", "interview", "offer", "accepted", "rejected", "no_reply", "withdrawn",
];

/** Still in play: waiting on them, or an offer waiting on you. */
export const OPEN_STATUSES: ApplicationStatus[] = ["applied", "screening", "interview", "offer"];

/** One dated change of status. */
export interface Step {
  id: string;
  status: ApplicationStatus;
  on_date: string;
  note: string | null;
}

/** A job application with its full step history; `status` is the latest step's. */
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
  /** When to chase it. */
  follow_up_on: string | null;
  /** Pay offered, in dollars; private to the owner. */
  offer_amount: number | null;
  offer_period: OfferPeriod | null;
  steps: Step[];
  /** Date of the latest step. */
  last_step_on: string;
  /** Waiting on them with no new step for 30 days: time to ask "no reply yet?". */
  quiet: boolean;
  /** The offer's pay is shared, with no name, toward the employer's typical pay. */
  salary_shared: boolean;
  /** When recorded, naive UTC. */
  created_at: string | null;
  updated_at: string | null;
}

/** Body to create or edit an application. */
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

/** Body to record a step. */
export interface StepInput {
  status: ApplicationStatus;
  on_date: string;
  note: string | null;
}

/** One Sankey band: how many moved between two stages; "waiting" marks still open. */
export interface Flow {
  source: string;
  target: string;
  count: number;
}

/** Figures for a set of applications, derived from their step histories. */
export interface ApplicationStats {
  total: number;
  /** Still at applied, screening, interview or offer. */
  open: number;
  /** Heard back at all: screening, interview, offer or rejection. */
  replied: number;
  /** `replied / total` as a fraction; null with nothing applied for. */
  reply_rate: number | null;
  /** Days from applying to the first reply, over those that replied. */
  median_days_to_reply: number | null;
  interviews: number;
  offers: number;
  accepted: number;
  /** Count per current status. */
  by_status: Record<string, number>;
  flows: Flow[];
}

/** A named recruiting season, month to month, both ends YYYY-MM. */
export interface Season {
  id: string;
  name: string;
  starts: string;
  ends: string;
}

/** Body to create or edit a season. */
export interface SeasonInput {
  name: string;
  starts: string;
  ends: string;
}

/** Typical hourly pay at one employer, from at least 5 verified shared offers. */
export interface SalaryFigure {
  /** The name as most people wrote it. */
  employer: string;
  /** Offers counted, a multiple of 5. */
  people: number;
  /** Dollars per hour. */
  median: number;
  /** Bottom of the middle half. */
  p25: number;
  /** Top of the middle half. */
  p75: number;
}
