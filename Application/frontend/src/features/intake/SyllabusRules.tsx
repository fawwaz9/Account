import { ConfirmedRule, ExtractedRule } from "./api";

export type RuleKind = "prerequisites" | "corequisites";
export type RuleDrafts = Record<RuleKind, { text: string; note: string }>;

const TITLE: Record<RuleKind, string> = { prerequisites: "Prerequisites", corequisites: "Co-requisites" };

/** Drafts to start from: what the reader found, in the typed form. */
export function draftsFrom(found: Partial<Record<RuleKind, ExtractedRule | null | undefined>>): RuleDrafts {
  return {
    prerequisites: { text: found.prerequisites?.text ?? "", note: found.prerequisites?.note ?? "" },
    corequisites: { text: found.corequisites?.text ?? "", note: found.corequisites?.note ?? "" },
  };
}

/** What to send: a kind only when its field is filled in. Cleared, nothing is
 *  filed -- nothing becomes a record without confirmation. */
export function confirmedRules(drafts: RuleDrafts, offered: Record<RuleKind, boolean>) {
  const out: { prerequisites?: ConfirmedRule; corequisites?: ConfirmedRule } = {};
  for (const kind of ["prerequisites", "corequisites"] as RuleKind[]) {
    const text = drafts[kind].text.trim();
    if (offered[kind] && text) out[kind] = { text, note: drafts[kind].note.trim() || null };
  }
  return out;
}

interface Props {
  readonly found: Partial<Record<RuleKind, ExtractedRule | null | undefined>>;
  readonly drafts: RuleDrafts;
  readonly onChange: (next: RuleDrafts) => void;
  /** Your current rule per kind, which confirming would replace. */
  readonly own?: Partial<Record<RuleKind, string | null | undefined>>;
}

/**
 * The prerequisites a syllabus states, editable before anything is filed
 * (Phase 2 item 5). Kept as your own rule; it reaches anyone else only after
 * review, and then as the rule alone -- never the syllabus's wording.
 */
export default function SyllabusRules({ found, drafts, onChange, own }: Props) {
  const kinds = (["prerequisites", "corequisites"] as RuleKind[]).filter((kind) => found[kind]);
  if (kinds.length === 0) return null;

  return (
    <fieldset className="syllabusRules">
      <legend className="small-text muted">What the syllabus says the course requires</legend>
      {kinds.map((kind) => {
        const stated = found[kind]!;
        return (
          <div key={kind} className="syllabusRule">
            <label>
              <span className="small-text muted">{TITLE[kind]}</span>
              <input className="--input" value={drafts[kind].text} maxLength={300} aria-label={TITLE[kind]}
                placeholder="CPSC 210 and one of MATH 200, MATH 217"
                onChange={(e) => onChange({ ...drafts, [kind]: { ...drafts[kind], text: e.target.value } })} />
            </label>
            <label>
              <span className="small-text muted">Anything else</span>
              <input className="--input" value={drafts[kind].note} maxLength={300} aria-label={`${TITLE[kind]} note`}
                onChange={(e) => onChange({ ...drafts, [kind]: { ...drafts[kind], note: e.target.value } })} />
            </label>
            {stated.sentence && <blockquote className="prereqQuote small-text">{stated.sentence}</blockquote>}
            {own?.[kind] && (
              <p className="small-text muted">
                {drafts[kind].text.trim()
                  ? `Replaces yours: ${own[kind]}`
                  : `Yours stays: ${own[kind]}. Type a rule here to replace it.`}
              </p>
            )}
          </div>
        );
      })}
      <p className="small-text muted">
        Kept as your own and checked against your courses. Clear a field to leave it out. Nobody else sees it
        unless it is reviewed, and then only the rule, never the syllabus&rsquo;s wording.
      </p>
    </fieldset>
  );
}
