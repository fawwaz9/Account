import { useEffect, useState } from "react";
import { fetchCatalogueLink, searchCatalogue, setCatalogueLink } from "../api";
import { CatalogueChoice, CatalogueCourse, CatalogueLink } from "../types";
import HelpTip from "../../../shared/components/HelpTip";

const CAMPUS: Record<string, string> = { UBCV: "UBC Vancouver", UBCO: "UBC Okanagan" };

export function catalogueCode(course: CatalogueCourse) {
  return `${course.subject} ${course.number}`;
}

function describe(course: CatalogueCourse) {
  const campus = CAMPUS[course.campus] ?? course.campus;
  return course.title ? `${catalogueCode(course)} · ${course.title} · ${campus}` : `${catalogueCode(course)} · ${campus}`;
}

const HOW: Record<CatalogueLink["how"], string> = {
  chosen: "your choice",
  matched: "matched by code",
  none_chosen: "",
  not_found: "",
};

interface CatalogueLineProps {
  readonly userId: string;
  readonly courseId: string;
}

/**
 * Which shared catalogue course this one is (Phase 2 item 3, D11).
 *
 * Automatic by campus and code until you choose; a choice of a course, or of
 * none, then wins. The link moves no grade -- it is what prerequisites hang
 * on. Says nothing when the read fails, like the other panels on this page.
 */
export default function CatalogueLine({ userId, courseId }: CatalogueLineProps) {
  const [link, setLink] = useState<CatalogueLink | null>(null);
  const [picking, setPicking] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CatalogueCourse[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCatalogueLink(userId, courseId)
      .then((found) => { if (!cancelled) setLink(found); })
      .catch(() => { if (!cancelled) setLink(null); });
    return () => { cancelled = true; };
  }, [userId, courseId]);

  useEffect(() => {
    if (!picking) return;
    let cancelled = false;
    searchCatalogue(userId, query)
      .then((rows) => { if (!cancelled) setResults(rows); })
      .catch(() => { if (!cancelled) setResults([]); });
    return () => { cancelled = true; };
  }, [picking, query, userId]);

  if (!link) return null;

  async function choose(choice: CatalogueChoice) {
    setSaving(true);
    setError(null);
    try {
      setLink(await setCatalogueLink(userId, courseId, choice));
      setPicking(false);
      setQuery("");
    } catch {
      setError("Couldn't save that. The link is as it was.");
    } finally {
      setSaving(false);
    }
  }

  const how = HOW[link.how];
  return (
    <div className="catalogueLine">
      <span className="catalogueLabel">Catalogue</span>
      {link.course ? (
        <span>
          {describe(link.course)}
          {how && <span className="muted"> ({how})</span>}
        </span>
      ) : link.how === "none_chosen" ? (
        <span className="muted">none, by your choice</span>
      ) : (
        <span className="muted">not listed yet</span>
      )}
      <HelpTip label="What the catalogue is">
        One shared list of courses, the same for everyone, that prerequisites are
        attached to. Your course is matched to it by campus and code; you can pick
        another, or none. It changes no grade, average or credit.
      </HelpTip>
      {!picking && (
        <button type="button" className="courseLinkAdd" onClick={() => setPicking(true)}>
          Change
        </button>
      )}
      {error && <p className="small-text error" role="alert">{error}</p>}

      {picking && (
        <div className="cataloguePicker">
          <label className="srOnly" htmlFor={`catalogue-search-${courseId}`}>Search the catalogue by code</label>
          <input
            id={`catalogue-search-${courseId}`}
            type="search"
            placeholder="Code, e.g. CPSC 221"
            value={query}
            maxLength={20}
            onChange={(event) => setQuery(event.target.value)}
            autoFocus
          />
          {results.length > 0 ? (
            <ul className="catalogueResults">
              {results.map((row) => (
                <li key={row.id}>
                  <button type="button" className="courseLinkAdd" disabled={saving}
                          onClick={() => void choose({ mode: "chosen", catalogue_course_id: row.id })}>
                    {describe(row)}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="small-text muted">Nothing in the catalogue starts like that.</p>
          )}
          <div className="catalogueActions">
            {link.how !== "none_chosen" && (
              <button type="button" className="calButton" disabled={saving}
                      onClick={() => void choose({ mode: "none" })}>
                None of these
              </button>
            )}
            {(link.how === "chosen" || link.how === "none_chosen") && (
              <button type="button" className="calButton" disabled={saving}
                      onClick={() => void choose({ mode: "auto" })}>
                Match by code
              </button>
            )}
            <button type="button" className="calButton" disabled={saving}
                    onClick={() => { setPicking(false); setQuery(""); }}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
