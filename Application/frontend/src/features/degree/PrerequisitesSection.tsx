import { useEffect, useRef, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import CatalogueLine from "../grades/components/CatalogueLine";
import PrerequisitesPanel, { STATUS_WORDS } from "../grades/components/PrerequisitesPanel";
import { fetchPrerequisiteSummaries, PrerequisiteSummary } from "./api";

/** A course's prerequisites in words; a course with no rule says so. */
function verdict(row: PrerequisiteSummary): string {
  return row.status ? STATUS_WORDS[row.status] : "No rule recorded";
}

/** Whether a course needs a look: a rule not met, or met only if what's under way goes to plan. */
function needsLook(row: PrerequisiteSummary): boolean {
  return row.status === "not_met" || row.status === "on_track";
}

/**
 * The degree audit's prerequisites (moved off the course page, 2026-11-07): the courses under
 * way or planned whose rules aren't met or are only on track, then the rest on request. Each
 * opens to its catalogue link and its rules, which can be edited there. Advisory only.
 */
export default function PrerequisitesSection({ userId }: { readonly userId: string }) {
  const [rows, setRows] = useState<PrerequisiteSummary[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const ticket = ++latest.current;
    fetchPrerequisiteSummaries(userId)
      .then((found) => { if (ticket === latest.current) setRows(found); })
      .catch(() => { if (ticket === latest.current) setRows(null); });
  }, [userId, refresh]);

  if (!rows || rows.length === 0) return null;
  const problems = rows.filter(needsLook);
  const rest = rows.filter((row) => !needsLook(row));

  function item(row: PrerequisiteSummary) {
    const expanded = open === row.course_id;
    return (
      <li key={row.course_id} className="degreePrereq">
        <button
          type="button"
          className="degreePrereqToggle"
          aria-expanded={expanded}
          onClick={() => setOpen(expanded ? null : row.course_id)}
        >
          {row.code}{row.name ? ` · ${row.name}` : ""}
        </button>
        <span className="small-text">
          {verdict(row)}
          {row.planned ? " · planned" : ""}
          {row.linked ? "" : " · not linked to the catalogue"}
        </span>
        {expanded && (
          <div className="degreePrereqDetail">
            <CatalogueLine userId={userId} courseId={row.course_id} />
            <PrerequisitesPanel userId={userId} courseId={row.course_id} onChanged={() => setRefresh((n) => n + 1)} />
          </div>
        )}
      </li>
    );
  }

  return (
    <section aria-label="Prerequisites" className="degreePrereqs">
      <h2>
        Prerequisites{" "}
        <HelpTip label="About prerequisites">
          For each course you&apos;re taking or planning: whether its prerequisites and co-requisites are met
          by your record. Your own version of a rule applies when you have one, the shared catalogue&apos;s
          otherwise. Advisory only: exceptions are made, and nothing is ever blocked.
        </HelpTip>
      </h2>
      {problems.length > 0 ? (
        <ul className="degreeList" aria-label="Courses to look at">{problems.map(item)}</ul>
      ) : (
        <p className="small-text">Every course you&apos;re taking or planning has its prerequisites met, or none recorded.</p>
      )}
      {rest.length > 0 && (
        <details className="degreePrereqRest">
          <summary className="small-text">Your other courses ({rest.length})</summary>
          <ul className="degreeList" aria-label="Other courses">{rest.map(item)}</ul>
        </details>
      )}
    </section>
  );
}
