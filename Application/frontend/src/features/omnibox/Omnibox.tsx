import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fileLine, previewLine } from "./api";
import { OMNIBOX_KIND_LABELS, OmniboxPreview, OmniboxResult } from "./types";
import { useAuth } from "../../app/auth/AuthContext";
import useDebounce from "../../shared/hooks/useDebounce";
import { dueLabel, duration } from "../../shared/utils/dateUtils";
import { formatMoney } from "../budget/money";

/** Where each kind lands, so the confirmation can offer to go and look. */
function destination(result: OmniboxResult): string {
  if (result.kind === "grade" && result.course_id) {
    return `/grades/courses/${result.course_id}`;
  }
  return result.kind === "expense" ? "/budget" : "/tasks";
}

/**
 * One input, anywhere: "coffee 4.50", "cosc121 midterm 78/100", "lab due fri".
 *
 * The module it is heading for is shown as a badge *before* you commit, which
 * is the whole reason this is safe to have. An omnibox that routes silently is
 * the one shape of this feature worth not building: filing a mark as an expense
 * is a mistake you would find weeks later, in a number you had stopped
 * questioning.
 *
 * Reachable with Ctrl/Cmd-K from any page, since the point is not having to be
 * on the right one.
 */
export default function Omnibox() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  const [text, setText] = useState("");
  const [preview, setPreview] = useState<OmniboxPreview | null>(null);
  const [filed, setFiled] = useState<OmniboxResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounced = useDebounce(text, 200);

  // Only the newest reading may land; typing fast fires several.
  const latestRequest = useRef(0);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (!user || debounced.trim() === "") {
      setPreview(null);
      return;
    }

    const ticket = ++latestRequest.current;
    previewLine(user.id, debounced)
      .then((next) => {
        if (ticket === latestRequest.current) setPreview(next);
      })
      .catch(() => {
        // A failed reading is not worth an error line: the box still works, and
        // submitting reports anything that actually goes wrong.
        if (ticket === latestRequest.current) setPreview(null);
      });
  }, [user, debounced]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || text.trim() === "" || preview?.can_create === false) return;

    setSaving(true);
    setError(null);
    try {
      const result = await fileLine(user.id, text);
      setFiled(result);
      setText("");
      setPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not file that");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="omnibox">
      <form onSubmit={handleSubmit} className="omniRow">
        {/* The badge sits before the input, so the module is read first -- it
            is the part a mis-file turns on. */}
        {preview && (
          <span className={`omniKind omniKind-${preview.kind}`}>
            {OMNIBOX_KIND_LABELS[preview.kind]}
          </span>
        )}

        <input
          ref={inputRef}
          className="omniInput"
          value={text}
          onChange={(event) => { setText(event.target.value); setFiled(null); setError(null); }}
          placeholder="coffee 4.50   ·   cosc121 midterm 78/100   ·   lab due fri"
          aria-label="Type anything: a task, an expense, or a mark"
          aria-describedby="omni-reading"
        />

        <button
          type="submit"
          className="calButton calButtonPrimary"
          disabled={saving || !text.trim() || preview?.can_create === false}
        >
          {saving ? "Filing..." : "File"}
        </button>
      </form>

      <div id="omni-reading" className="omniReading" aria-live="polite">
        {error && <span className="calError">{error}</span>}

        {!error && filed && (
          <>
            <span className="omniDone">Filed: {filed.summary}</span>
            <button
              type="button"
              className="omniLink"
              onClick={() => navigate(destination(filed))}
            >
              Go to it
            </button>
          </>
        )}

        {!error && !filed && preview && preview.can_create && (
          <>
            <span className="omniSummary">{preview.summary}</span>
            {preview.amount !== null && (
              <span className="omniChip">{formatMoney(preview.amount)}</span>
            )}
            {preview.on_date && preview.kind !== "expense" && (
              <span className="omniChip">{dueLabel(preview.on_date)}</span>
            )}
            {preview.estimated_minutes && (
              <span className="omniChip">{duration(preview.estimated_minutes)}</span>
            )}
            {preview.unmatched_course && (
              <span className="omniWarn">
                no course matches "{preview.unmatched_course}"
              </span>
            )}
          </>
        )}

        {/* The reason always says what to do about it, not just what is wrong. */}
        {!error && !filed && preview && !preview.can_create && (
          <span className="omniWarn">{preview.reason ?? preview.summary}</span>
        )}

        {!error && !filed && !preview && (
          <span className="muted omniHint">
            A mark goes to Grades, an amount to Budget, anything else to Tasks.
            <kbd className="omniKbd">⌘K</kbd>
          </span>
        )}
      </div>
    </div>
  );
}
