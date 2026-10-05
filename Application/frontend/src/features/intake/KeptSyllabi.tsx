import { useEffect, useRef, useState } from "react";
import { fetchCourseSyllabi, fetchSyllabusFile, KeptSyllabus } from "./api";

interface KeptSyllabiProps {
  readonly userId: string;
  readonly courseId: string;
}

/**
 * The syllabus a course was built from, kept as the original file (Phase 1
 * D24). Silent when none was kept -- a course typed in by hand has nothing to
 * show, and saying so is not information.
 *
 * Fetched with the session's token and saved from a blob: the file route is
 * authenticated like every other, so a plain link could not reach it.
 */
export default function KeptSyllabi({ userId, courseId }: KeptSyllabiProps) {
  const [kept, setKept] = useState<KeptSyllabus[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  useEffect(() => {
    const ticket = ++latest.current;
    fetchCourseSyllabi(userId, courseId)
      .then((rows) => { if (ticket === latest.current) setKept(rows); })
      .catch(() => { if (ticket === latest.current) setKept([]); });
  }, [userId, courseId]);

  async function download(item: KeptSyllabus) {
    setBusy(item.id);
    setError(null);
    try {
      const blob = await fetchSyllabusFile(userId, item.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = item.filename || "syllabus";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("Couldn't download the syllabus.");
    } finally {
      setBusy(null);
    }
  }

  if (kept.length === 0) return null;

  return (
    <div className="courseLinks" aria-label="Kept syllabi">
      {kept.map((item) => (
        <button
          key={item.id}
          type="button"
          className="courseLink"
          onClick={() => void download(item)}
          disabled={busy !== null}
        >
          {busy === item.id ? "Downloading…" : `Syllabus${item.filename ? ` · ${item.filename}` : ""}`}
        </button>
      ))}
      {error && <p className="small-text error" role="alert">{error}</p>}
    </div>
  );
}
