import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { updateCourse } from "../api";
import { CourseLink } from "../types";
import { getErrorMessage } from "./AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";

/** Link names offered on every course, pre-filled; a suggestion left empty saves nothing. */
const SUGGESTED = ["Canvas", "Piazza", "PrairieLearn"] as const;

/** One editor row. */
interface Row {
  title: string;
  url: string;
  /** A suggested row keeps its name fixed; a custom one can be renamed. */
  fixed: boolean;
}

/** Whether the dialog is open, the course and its links, and close and saved callbacks. */
interface CourseLinksModalProps {
  readonly open: boolean;
  readonly courseId: string;
  readonly links: readonly CourseLink[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/**
 * Editor rows: the suggestions first, filled from stored links of the same name in any case,
 * then every other stored link as a custom row.
 */
function rowsFor(links: readonly CourseLink[]): Row[] {
  const used = new Set<number>();

  const suggested: Row[] = SUGGESTED.map((title) => {
    const at = links.findIndex(
      (link, index) => !used.has(index) && link.title.toLowerCase() === title.toLowerCase()
    );
    if (at !== -1) used.add(at);
    return { title, url: at === -1 ? "" : links[at].url, fixed: true };
  });

  const custom: Row[] = links
    .filter((_, index) => !used.has(index))
    .map((link) => ({ title: link.title, url: link.url, fixed: false }));

  return [...suggested, ...custom];
}

/**
 * Editor for a course's links, saved whole through `updateCourse`.
 * Rows missing a name or an address are left out of the save.
 */
export default function CourseLinksModal({
  open,
  courseId,
  links,
  onClose,
  onSaved,
}: CourseLinksModalProps) {
  const { user } = useAuth();
  const [rows, setRows] = useState<Row[]>(() => rowsFor(links));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows(rowsFor(links));
    setError(null);
  }, [links, open]);

  if (!open) return null;

  function update(index: number, field: "title" | "url", value: string) {
    setRows((current) =>
      current.map((row, at) => (at === index ? { ...row, [field]: value } : row))
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    // An empty box is not a link. A suggested row nobody filled in disappears
    // rather than being stored as a title with nowhere to go.
    const payload: CourseLink[] = rows
      .map((row) => ({ title: row.title.trim(), url: row.url.trim() }))
      .filter((row) => row.title !== "" && row.url !== "");

    setSaving(true);
    setError(null);
    try {
      await updateCourse(user.id, courseId, { links: payload });
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="Course links" onClose={onClose}>
      <form className="calForm linksForm" onSubmit={handleSubmit}>
        <p className="taskEditNote">
          Anything with an empty address is left out. Addresses without
          http:// are assumed to be https.
        </p>

        {rows.map((row, index) => (
          <div className="linkRow" key={row.fixed ? row.title : `custom-${index}`}>
            {row.fixed ? (
              <span className="linkRowName">{row.title}</span>
            ) : (
              <input
                className="calInput linkRowTitle"
                value={row.title}
                onChange={(event) => update(index, "title", event.target.value)}
                placeholder="Name"
                aria-label={`Name of link ${index + 1}`}
              />
            )}

            <input
              className="calInput"
              type="url"
              value={row.url}
              onChange={(event) => update(index, "url", event.target.value)}
              placeholder={`https://${row.title.toLowerCase() || "example"}.com`}
              aria-label={`Address for ${row.title || `link ${index + 1}`}`}
            />
          </div>
        ))}

        <button
          type="button"
          className="courseLinkAdd"
          onClick={() => setRows((current) => [...current, { title: "", url: "", fixed: false }])}
        >
          Add new link
        </button>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
