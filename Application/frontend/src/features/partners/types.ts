/** Accountability partners (Phase 2 item 10): completion, never outcomes. */
export interface Figure {
  week_percent: number | null;
  streak_weeks: number;
  figure_on: string | null;
}

export interface Partner {
  partner_id: string;
  name: string;
  since: string;
  /** Null until they have opened the app since you became partners. */
  figure: Figure | null;
}

export interface OpenInvite {
  id: string;
  created_at: string;
  expires_at: string;
}

export interface Partners {
  mine: Figure;
  partners: Partner[];
  invites: OpenInvite[];
}

export interface NewInvite {
  id: string;
  token: string;
  expires_at: string;
}

export type AcceptStatus = "accepted" | "invalid" | "own" | "already";
