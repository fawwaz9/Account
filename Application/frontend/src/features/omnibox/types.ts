/** Omnibox (quick add) types; mirrors app/Omnibox/schemas/omnibox.py. */

/** What one typed line can become. */
export type OmniboxKind = "task" | "expense" | "grade";

/** Display label per kind. */
export const OMNIBOX_KIND_LABELS: Record<OmniboxKind, string> = {
  task: "Task",
  expense: "Expense",
  grade: "Grade",
};

/**
 * What one line was read as and what filing it would do.
 * Flat across kinds: fields another kind uses stay null.
 */
export interface OmniboxPreview {
  text: string;
  kind: OmniboxKind;
  /** One sentence saying what will happen. */
  summary: string;
  can_create: boolean;
  /** Why it cannot be filed, phrased as something to do about it. */
  reason: string | null;

  title: string;
  on_date: string | null;
  course_id: string | null;
  course_code: string | null;
  /** A typed course code that matched none of yours, or several. */
  unmatched_course: string | null;

  /** Task only. */
  estimated_minutes: number | null;

  /** Expense only, in dollars. */
  amount: number | null;
  account_id: string | null;
  account_name: string | null;
  category_id: string | null;
  category_name: string | null;

  /** Grade only. */
  score: number | null;
  max_score: number | null;
  grade_category: string | null;

  /** Kinds the parser recognised, for debugging a bad reading. */
  matched: string[];
}

/** What was filed, and where to find it. */
export interface OmniboxResult {
  kind: OmniboxKind;
  id: string;
  /** Set for a grade, to link to its course. */
  course_id: string | null;
  summary: string;
  preview: OmniboxPreview;
}
