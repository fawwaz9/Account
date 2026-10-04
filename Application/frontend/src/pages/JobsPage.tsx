import { useMemo, useState } from "react";
import JobCard from "../features/jobs/components/JobCard";
import JobModal from "../features/jobs/components/JobModal";
import ShiftList from "../features/jobs/components/ShiftList";
import ShiftScheduleModal from "../features/jobs/components/ShiftScheduleModal";
import ConfirmShiftModal from "../features/jobs/components/ConfirmShiftModal";
import Earnings from "../features/jobs/components/Earnings";
import PaychequeList from "../features/jobs/components/PaychequeList";
import PaychequeModal from "../features/jobs/components/PaychequeModal";
import DeleteConfirmModal from "../features/grades/components/DeleteConfirmModal";
import { useJobs } from "../features/jobs/hooks/useJobs";
import { deleteShift } from "../features/jobs/api";
import { Job, Paycheque, ShiftOccurrence } from "../features/jobs/types";
import { useAuth } from "../app/auth/AuthContext";
import { useShortcut } from "../shared/hooks/useShortcut";
import "../styles/calendar.css";
import "../styles/jobs.css";

/**
 * The jobs page.
 *
 * Time and money are deliberately split across the app rather than gathered
 * here: a shift is a block on the calendar because it competes with lectures
 * for the same hours, and a paycheque is a line in the ledger because that is
 * where money that actually moved belongs. What lives here is everything about
 * the jobs themselves -- what they are, when they are worked, and (from the
 * next stage) what they earn.
 */
export default function JobsPage() {
  const { user } = useAuth();
  const [showArchived, setShowArchived] = useState(false);
  const { jobs, shifts, paycheques, earnings, loading, error, reload } = useJobs(showArchived);

  const [editing, setEditing] = useState<Job | null>(null);
  const [adding, setAdding] = useState(false);
  const [scheduling, setScheduling] = useState<Job | null>(null);
  const [confirming, setConfirming] = useState<ShiftOccurrence | null>(null);
  const [payingCheque, setPayingCheque] = useState<Paycheque | null>(null);
  const [recordingPay, setRecordingPay] = useState(false);
  const [removingShift, setRemovingShift] = useState(false);

  useShortcut("n", () => { setEditing(null); setAdding(true); });
  // The tenth unconfirmed delete, missed by the audit of nine: removing a shift
  // is permanent, and the hours it carried leave the earnings figures with it.
  const [removingTarget, setRemovingTarget] = useState<ShiftOccurrence | null>(null);
  const [shiftError, setShiftError] = useState<string | null>(null);

  async function handleRemoveShift(shift: ShiftOccurrence) {
    setRemovingTarget(null);
    if (!user) return;
    // A confirmed shift can carry a cash tip already in the ledger, so removing
    // one is worth a beat of friction rather than a single unprotected click.
    if (
      shift.confirmed &&
      !window.confirm(
        `Remove the ${shift.job_name} shift on ${shift.on_date}? ` +
          "Anything already confirmed for it, including a cash tip in your budget, goes with it."
      )
    ) {
      return;
    }

    setRemovingShift(true);
    setShiftError(null);
    try {
      await deleteShift(user.id, shift.event_id);
      await reload();
    } catch (err) {
      setShiftError(err instanceof Error ? err.message : "Could not remove that shift");
    } finally {
      setRemovingShift(false);
    }
  }

  // Minutes per job across the window, so a card can say what it is worth in
  // time without every card filtering the same list again.
  const hoursByJob = useMemo(() => {
    const totals = new Map<string, number>();
    for (const shift of shifts) {
      totals.set(shift.job_id, (totals.get(shift.job_id) ?? 0) + shift.counted_minutes);
    }
    return totals;
  }, [shifts]);

  return (
    <div className="container">
      <div className="calTopbar">
        <h1 className="title">Jobs</h1>
        <div className="jobTopActions">
          <label className="taskToggle">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(event) => setShowArchived(event.target.checked)}
            />
            Show archived
          </label>
          <button
            type="button"
            className="calButton calButtonPrimary"
            onClick={() => { setEditing(null); setAdding(true); }}
          >
            Add a job
          </button>
        </div>
      </div>

      {error && <p className="calError">{error}</p>}
      {loading && jobs.length === 0 && <p className="calMuted" role="status">Loading…</p>}

      <Earnings earnings={earnings} />

      {!loading && jobs.length === 0 ? (
        <p className="calMuted">
          No jobs yet. Add one, then give it a shift pattern and it will appear on
          your calendar beside your classes.
        </p>
      ) : (
        <ul className="jobGrid">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              hours={hoursByJob.get(job.id) ?? 0}
              onEdit={(next) => { setEditing(next); setAdding(true); }}
              onSchedule={setScheduling}
              busy={loading}
            />
          ))}
        </ul>
      )}

      {jobs.length > 0 && (
        // Side by side: what you have worked and what has arrived for it are
        // the same story from two ends, and reading them as one column put
        // several paycheque rows between a shift and the reason to look at it.
        <div className="jobSplit">
          <div>
            {shiftError && <p className="calError">{shiftError}</p>}
            <ShiftList
              shifts={shifts}
              onConfirm={setConfirming}
              onRemove={setRemovingTarget}
              busy={loading || removingShift}
            />
          </div>

          <PaychequeList
            paycheques={paycheques}
            onAdd={() => { setPayingCheque(null); setRecordingPay(true); }}
            onEdit={(cheque) => { setPayingCheque(cheque); setRecordingPay(true); }}
            busy={loading}
          />
        </div>
      )}

      <JobModal
        open={adding}
        job={editing}
        onClose={() => { setAdding(false); setEditing(null); }}
        onSaved={reload}
      />

      <ShiftScheduleModal
        job={scheduling}
        onClose={() => setScheduling(null)}
        onSaved={reload}
      />

      <ConfirmShiftModal
        shift={confirming}
        onClose={() => setConfirming(null)}
        onSaved={reload}
      />

      <PaychequeModal
        open={recordingPay}
        jobs={jobs}
        paycheque={payingCheque}
        onClose={() => { setRecordingPay(false); setPayingCheque(null); }}
        onSaved={reload}
      />

      <DeleteConfirmModal
        open={removingTarget !== null}
        title="Remove this shift?"
        message={
          removingTarget
            ? `The shift on ${removingTarget.on_date} will be removed, and the hours ` +
              `it carried will leave your earnings figures with it. A paycheque ` +
              `already recorded stays — that money moved.`
            : ""
        }
        confirmLabel="Remove the shift"
        submitting={removingShift}
        error={shiftError}
        onCancel={() => setRemovingTarget(null)}
        onConfirm={() => { if (removingTarget) void handleRemoveShift(removingTarget); }}
      />
    </div>
  );
}
