import { useEffect, useRef, useState } from "react";
import { captureTask, previewCapture } from "../api";
import { QuickCapturePreview } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { useShortcut } from "../../../shared/hooks/useShortcut";
import useDebounce from "../../../shared/hooks/useDebounce";
import { dueLabel, duration } from "../../../shared/utils/dateUtils";

/** Called after a line becomes a task. */
interface QuickCaptureProps {
  readonly onCaptured: () => void;
}

/**
 * One box that turns "cosc121 lab due fri" into a task, showing the server's reading as you type.
 * The N shortcut focuses it, and only the newest preview is shown.
 */
export default function QuickCapture({ onCaptured }: QuickCaptureProps) {
  const { user } = useAuth();
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<QuickCapturePreview | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounced = useDebounce(text, 200);
  const inputRef = useRef<HTMLInputElement>(null);

  // N on the Tasks page lands here: this box is the page's fast way to add.
  useShortcut("n", () => inputRef.current?.focus());

  // Only the newest preview may land. Typing fast fires several, and without
  // this an earlier reading can resolve last and sit under later text.
  const latestRequest = useRef(0);

  useEffect(() => {
    if (!user || debounced.trim() === "") {
      setPreview(null);
      return;
    }

    const ticket = ++latestRequest.current;
    previewCapture(user.id, debounced)
      .then((next) => {
        if (ticket === latestRequest.current) setPreview(next);
      })
      .catch(() => {
        // A failed preview is not worth an error message: the box still works,
        // and submitting reports anything that actually goes wrong.
        if (ticket === latestRequest.current) setPreview(null);
      });
  }, [user, debounced]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || text.trim() === "") return;

    setSaving(true);
    setError(null);
    try {
      await captureTask(user.id, text);
      setText("");
      setPreview(null);
      onCaptured();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read that");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="captureForm" onSubmit={handleSubmit}>
      <div className="captureRow">
        <input
          ref={inputRef}
          className="taskInput taskInputWide"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="cosc121 lab due fri 90m"
          aria-label="Quick capture: type a task in plain words"
          // The reading below is the live description of this field, so a
          // screen reader hears the guess change rather than only seeing it.
          aria-describedby="capture-reading"
        />
        <button
          type="submit"
          className="calButton calButtonPrimary"
          disabled={saving || !text.trim() || preview?.can_create === false}
        >
          {saving ? "Adding..." : "Add"}
        </button>
      </div>

      <p id="capture-reading" className="captureReading" aria-live="polite">
        {error && <span className="calError">{error}</span>}

        {!error && preview && preview.can_create && (
          <>
            <span className="captureTitle">{preview.title}</span>
            {preview.course_code && (
              <span className="taskTag taskTagCourse">{preview.course_code}</span>
            )}
            {preview.due_date && (
              <span className="captureChip">{dueLabel(preview.due_date)}</span>
            )}
            {preview.estimated_minutes && (
              <span className="captureChip">{duration(preview.estimated_minutes)}</span>
            )}
            {/* Said plainly, because a code that matched nothing is the one
                mistake this box can make that the student cannot see. */}
            {preview.unmatched_course && (
              <span className="captureWarn">
                no course matches "{preview.unmatched_course}" — kept in the title
              </span>
            )}
          </>
        )}

        {!error && preview && !preview.can_create && (
          <span className="muted">That is all date and no task — add what to do.</span>
        )}

        {!error && !preview && (
          <span className="muted">
            Course code, a day, and how long: "cosc121 lab due fri 90m".
          </span>
        )}
      </p>
    </form>
  );
}
