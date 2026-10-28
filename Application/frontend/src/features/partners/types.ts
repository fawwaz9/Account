/** Completion, never outcomes: this week's share of tasks done and the good-week streak. */
export interface Figure {
  /** Percent of this week's due tasks done; null when nothing was due. */
  week_percent: number | null;
  /** Consecutive earlier weeks at 80% or more. */
  streak_weeks: number;
  /** Day it was measured; null if never. */
  figure_on: string | null;
}

/** An accountability partner and their figure. */
export interface Partner {
  partner_id: string;
  name: string;
  /** When the partnership began, naive UTC. */
  since: string;
  /** Null until they have opened the app since you became partners. */
  figure: Figure | null;
}

/** An unused invite link of yours. */
export interface OpenInvite {
  id: string;
  created_at: string;
  expires_at: string;
}

/** Your figure, your partners and your open invites. */
export interface Partners {
  mine: Figure;
  partners: Partner[];
  invites: OpenInvite[];
}

/** A new invite; its token is shown only here, and only its hash is kept. */
export interface NewInvite {
  id: string;
  token: string;
  expires_at: string;
}

/** Outcome of opening a partner invite link. */
export type AcceptStatus = "accepted" | "invalid" | "own" | "already";
