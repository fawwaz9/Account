/** Mirrors app/Omnibox/schemas/omnibox.py. */

export type OmniboxKind = "task" | "expense" | "grade";

export const OMNIBOX_KIND_LABELS: Record<OmniboxKind, string> = {
  task: "Task",
  expense: "Expense",
  grade: "Grade",
};

/**
 * What one line was read as, and what filing it would do.
 *
 * Flat rather than a union per kind: the view renders whichever fields are set
 * and ignores the rest, which beats switching on a discriminator to draw three
 * nearly identical rows.
 */
export interface OmniboxPreview {
  text: string;
  kind: OmniboxKind;
  /** One sentence saying what will happen. */
  summary: string;
  can_create: boolean;
  /** Why not, when it cannot — always phrased as something to do about it. */
  reason: string | null;

  title: string;
  on_date: string | null;
  course_id: string | null;
  course_code: string | null;
  unmatched_course: string | null;

  estimated_minutes: number | null;

  amount: number | null;
  account_id: string | null;
  account_name: string | null;
  category_id: string | null;
  category_name: string | null;

  score: number | null;
  max_score: number | null;
  grade_category: string | null;

  matched: string[];
}

export interface OmniboxResult {
  kind: OmniboxKind;
  id: string;
  /** Set for a grade, so the result can link to the course it landed on. */
  course_id: string | null;
  summary: string;
  preview: OmniboxPreview;
}
