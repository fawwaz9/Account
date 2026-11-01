import { useEffect, useRef, useState } from "react";
import { fetchGradeScenario } from "../api";
import { GradeScenario } from "../types";
import { getErrorMessage } from "./AddCourseModal";
import Modal from "../../../shared/components/Modal";

/** The course, its grade now, and the close handler. */
interface GradeScenarioModalProps {
  readonly userId: string;
  readonly courseId: string;
  readonly courseCode: string;
  /** Where the course stands now; the starting point for "everything else". */
  readonly current: number;
  readonly onClose: () => void;
}

/** How long to wait after the last slider move before asking the server. */
const SETTLE_MS = 200;

/**
 * Grade scenarios (Phase 4 item 10, §13.6): a slider on each unmarked assessment and
 * one for everything else, with the projected grade from the server's own engine.
 * Nothing is saved; closing it forgets the scenario.
 */
export default function GradeScenarioModal({ userId, courseId, courseCode, current, onClose }: GradeScenarioModalProps) {
  const [assume, setAssume] = useState(() => Math.round(current));
  const [scores, setScores] = useState<Record<string, number>>({});
  const [result, setResult] = useState<GradeScenario | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Sliders move faster than the server answers; only the newest answer may land.
  const latest = useRef(0);

  useEffect(() => {
    const ticket = ++latest.current;
    const timer = window.setTimeout(() => {
      fetchGradeScenario(userId, courseId, { assume, scores })
        .then((answer) => {
          if (ticket !== latest.current) return;
          setResult(answer);
          setError(null);
        })
        .catch((err) => {
          if (ticket === latest.current) setError(getErrorMessage(err));
        });
    }, SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [userId, courseId, assume, scores]);

  function setScore(gradeId: string, value: number) {
    setScores((was) => ({ ...was, [gradeId]: value }));
  }

  function clearScore(gradeId: string) {
    setScores((was) => {
      const next = { ...was };
      delete next[gradeId];
      return next;
    });
  }

  const delta = result ? Math.round((result.projected - result.current) * 100) / 100 : 0;

  return (
    <Modal title={`What if… ${courseCode}`} onClose={onClose} panelClassName="scenarioPanel">
      <p className="muted small-text">
        Set a score on any work still to come. Nothing here is saved.
      </p>

      <div className="scenarioOutcome" aria-live="polite">
        {result ? (
          <>
            <span className="scenarioProjected">{result.projected}%</span>
            {result.letter && <span className="scenarioLetter">{result.letter}</span>}
            <span className="scenarioDelta muted small-text">
              {delta === 0 ? "same as now" : `${delta > 0 ? "+" : ""}${delta} from ${result.current}% now`}
            </span>
          </>
        ) : (
          <span className="muted small-text">Working…</span>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      <label className="scenarioRow scenarioEverything">
        <span className="scenarioName">Everything else</span>
        <input
          type="range" min={0} max={100} step={1} value={assume}
          onChange={(event) => setAssume(Number(event.target.value))}
          aria-label="Score for everything you haven't set"
        />
        <span className="scenarioValue">{assume}%</span>
      </label>

      {result && result.items.length > 0 && (
        <ul className="scenarioList">
          {result.items.map((item) => {
            const isSet = item.grade_id in scores;
            const value = isSet ? scores[item.grade_id] : assume;
            return (
              <li key={item.grade_id} className={isSet ? "scenarioRow scenarioSet" : "scenarioRow"}>
                <span className="scenarioName">
                  {item.name}
                  <span className="muted small-text">
                    {item.category}{item.due_date ? ` · due ${item.due_date}` : ""}
                  </span>
                </span>
                <input
                  type="range" min={0} max={100} step={1} value={value}
                  onChange={(event) => setScore(item.grade_id, Number(event.target.value))}
                  aria-label={`Score for ${item.name}`}
                />
                <span className="scenarioValue">
                  {value}%
                  {isSet && (
                    <button type="button" className="scenarioReset" onClick={() => clearScore(item.grade_id)}
                      aria-label={`Put ${item.name} back with everything else`}>
                      ×
                    </button>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {result && (
        <ul className="scenarioAssumptions muted small-text">
          {result.assumptions.map((line) => <li key={line}>{line}</li>)}
          <li>It can still finish anywhere from {result.worst}% to {result.best}%.</li>
        </ul>
      )}

      <div className="flex justify-end gap-3 pt-4">
        <button type="button" onClick={onClose}
          className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200">
          Close
        </button>
      </div>
    </Modal>
  );
}
