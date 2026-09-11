import { useEffect, useState } from "react";
import { fetchRequiredFinal } from "../api";
import { RequiredFinal } from "../types";
import { getErrorMessage } from "./AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";
import Modal from "../../../shared/components/Modal";

interface RequiredFinalModalProps {
  readonly open: boolean;
  readonly courseId: string;
  readonly courseCode: string;
  readonly onClose: () => void;
}

export default function RequiredFinalModal({
  open,
  courseId,
  courseCode,
  onClose,
}: RequiredFinalModalProps) {
  const { user } = useAuth();
  const [target, setTarget] = useState("");
  const [result, setResult] = useState<RequiredFinal | null>(null);
  const [askedFor, setAskedFor] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Start clean each time it opens, so a previous course's answer never
  // lingers next to a new question.
  useEffect(() => {
    if (open) {
      setTarget("");
      setResult(null);
      setAskedFor(null);
      setError(null);
    }
  }, [open]);

  if (!open) return null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    const desired = Number(target);
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const answer = await fetchRequiredFinal(user.id, courseId, desired);
      setResult(answer);
      setAskedFor(desired);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal title="Required Final Grade" onClose={onClose}>
      <p className="muted small-text">
        What do you want to finish {courseCode} with?
      </p>

      <form className="requiredFinalForm" onSubmit={handleSubmit}>
        <div className="requiredFinalRow">
          <input
            id="target-grade"
            className="--input requiredFinalInput"
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            placeholder="Desired grade"
            aria-label="Desired final grade"
            required
          />
          <button type="submit" className="finalGradeButton" disabled={loading}>
            {loading ? "Working..." : "Calculate"}
          </button>
        </div>
      </form>

      {error && <p className="error">{error}</p>}

      {result && askedFor !== null && (
        <div className="requiredFinalResult">
          <RequiredFinalAnswer result={result} target={askedFor} />

          {result.unfinished_categories.length > 0 && (
            <p className="muted small-text requiredFinalCaveat">
              Not counted yet, because nothing in{" "}
              {result.unfinished_categories.join(", ")} has been marked.
            </p>
          )}
        </div>
      )}

      <div className="flex justify-end gap-3 pt-4">
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200"
        >
          Close
        </button>
      </div>
    </Modal>
  );
}

function RequiredFinalAnswer({
  result,
  target,
}: {
  readonly result: RequiredFinal;
  readonly target: number;
}) {
  // Already there: the maths returns a negative or zero requirement.
  if (result.needed <= 0) {
    return (
      <p className="requiredFinalGood">
        You have already secured {target}%. Anything on the final keeps you there.
      </p>
    );
  }

  // Out of reach: even a perfect final falls short.
  if (!result.possible) {
    return (
      <p className="requiredFinalBad">
        {target}% is out of reach — it would take{" "}
        <strong>{result.needed}%</strong> on the final.
      </p>
    );
  }

  return (
    <p className="requiredFinalScore">
      You need <strong>{result.needed}%</strong> on the final to finish at {target}%.
    </p>
  );
}
