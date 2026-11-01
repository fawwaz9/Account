import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../app/auth/AuthContext";
import HelpTip from "../../shared/components/HelpTip";
import { planNextTerm, searchCatalogue } from "../../features/grades/api";
import { CatalogueCourse, NextTermPlan } from "../../features/grades/types";
import { intelLines } from "../../features/grades/components/ClassFigures";
import { getErrorMessage } from "../../features/grades/components/AddCourseModal";

/** Candidates a plan may hold; the server's limit too. */
const MAX_CANDIDATES = 8;

/** A RateMyProfessors search for a name you typed: a link out, nothing fetched (§13.6). */
export function professorLink(name: string): string {
  return `https://www.ratemyprofessors.com/search/professors?q=${encodeURIComponent(name.trim())}`;
}

/**
 * The next-term planner (Phase 4 item 12, §13.6): pick candidate courses from the
 * catalogue and see past students' figures added up, above the floor only.
 */
export default function NextTermPage() {
  const { user } = useAuth();
  // The id, not the object: effects keyed on it don't rerun when the user is re-read.
  const userId = user?.id;
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<CatalogueCourse[]>([]);
  const [picked, setPicked] = useState<CatalogueCourse[]>([]);
  const [plan, setPlan] = useState<NextTermPlan | null>(null);
  const [professors, setProfessors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId || query.trim().length < 2) { setMatches([]); return; }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchCatalogue(userId, query.trim())
        .then((found) => { if (!cancelled) setMatches(found); })
        .catch(() => { if (!cancelled) setMatches([]); });
    }, 200);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [userId, query]);

  useEffect(() => {
    if (!userId || picked.length === 0) { setPlan(null); return; }
    let cancelled = false;
    planNextTerm(userId, picked.map((c) => c.id))
      .then((answer) => { if (!cancelled) { setPlan(answer); setError(null); } })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [userId, picked]);

  function add(course: CatalogueCourse) {
    if (picked.some((c) => c.id === course.id) || picked.length >= MAX_CANDIDATES) return;
    setPicked([...picked, course]);
    setQuery("");
    setMatches([]);
  }

  function remove(id: string) {
    setPicked(picked.filter((c) => c.id !== id));
  }

  return (
    <div className="container nextTermPage">
      <div className="gradesMenu">
        <h1 className="gradesTitle">
          Next term{" "}
          <HelpTip label="Where these figures come from">
            Hours, difficulty and the rest are what past students said in their end-of-term reviews, shown
            only once enough of them answered. They are other people&apos;s terms, so yours will differ.
          </HelpTip>
        </h1>
        <Link to="/grades" className="calButton">Back to grades</Link>
      </div>

      <label className="nextTermSearch">
        <span className="srOnly">Add a course</span>
        <input
          className="nextTermInput" type="search" value={query} maxLength={20}
          placeholder={picked.length >= MAX_CANDIDATES ? `Up to ${MAX_CANDIDATES} courses` : "Add a course, e.g. CPSC 221"}
          disabled={picked.length >= MAX_CANDIDATES}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search the catalogue"
        />
      </label>
      {matches.length > 0 && (
        <ul className="nextTermMatches" role="listbox" aria-label="Catalogue matches">
          {matches.map((course) => (
            <li key={course.id}>
              <button type="button" onClick={() => add(course)}>
                <strong>{course.subject} {course.number}</strong>{" "}
                <span className="muted small-text">{course.campus}{course.title ? ` · ${course.title}` : ""}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="error">{error}</p>}

      {plan && picked.length > 0 && (
        <>
          <section className="nextTermTotals" aria-label="This combination">
            {plan.total_hours !== null ? (
              <p className="nextTermHeadline">
                About <strong>{plan.total_hours} hours a week</strong>
                {plan.courses_with_hours < plan.courses.length && (
                  <span className="muted"> across {plan.courses_with_hours} of {plan.courses.length} courses</span>
                )}
              </p>
            ) : (
              <p className="nextTermHeadline muted">No hours figure yet for these courses.</p>
            )}
            <p className="small-text muted">
              {plan.total_credits > 0 && `${plan.total_credits} credits`}
              {plan.mean_difficulty !== null && ` · difficulty ${plan.mean_difficulty} / 5 on average`}
            </p>
          </section>

          <ul className="nextTermList">
            {plan.courses.map((course) => {
              const lines = course.intel ? intelLines(course.intel) : [];
              const name = professors[course.catalogue_id] ?? "";
              return (
                <li key={course.catalogue_id} className="nextTermCourse">
                  <div className="nextTermCourseHead">
                    <span>
                      <strong>{course.code}</strong>{" "}
                      <span className="muted small-text">{course.campus}{course.title ? ` · ${course.title}` : ""}</span>
                    </span>
                    <button type="button" className="nextTermRemove" onClick={() => remove(course.catalogue_id)}
                      aria-label={`Take ${course.code} out`}>×</button>
                  </div>
                  {lines.length > 0 ? (
                    <dl className="nextTermFigures">
                      {lines.map((line) => (
                        <div key={line.label}>
                          <dt>{line.label}</dt>
                          <dd>{line.value} <span className="muted small-text">({line.from})</span></dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p className="small-text muted">Not enough reviews yet (needs {plan.floor}).</p>
                  )}
                  <div className="nextTermProf">
                    <input
                      className="nextTermInput" type="text" value={name} maxLength={60}
                      placeholder="Instructor, if you know"
                      onChange={(event) => setProfessors({ ...professors, [course.catalogue_id]: event.target.value })}
                      aria-label={`Instructor for ${course.code}`}
                    />
                    {name.trim() && (
                      <a href={professorLink(name)} target="_blank" rel="noopener noreferrer" className="small-text">
                        Look up on RateMyProfessors
                      </a>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>

          <ul className="nextTermAssumptions small-text muted">
            {plan.assumptions.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </>
      )}
    </div>
  );
}
