import { useMemo, useState } from "react";
import JobCard from "../features/jobs/components/JobCard";
import JobModal from "../features/jobs/components/JobModal";
import ShiftList from "../features/jobs/components/ShiftList";
import ShiftScheduleModal from "../features/jobs/components/ShiftScheduleModal";
import ConfirmShiftModal from "../features/jobs/components/ConfirmShiftModal";
import Earnings from "../features/jobs/components/Earnings";
import PaychequeList from "../features/jobs/components/PaychequeList";
import PaychequeModal from "../features/jobs/components/PaychequeModal";
import { useJobs } from "../features/jobs/hooks/useJobs";
import { Job, Paycheque, ShiftOccurrence } from "../features/jobs/types";
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
  const [showArchived, setShowArchived] = useState(false);
  const { jobs, shifts, paycheques, earnings, loading, error, reload } = useJobs(showArchived);

  const [editing, setEditing] = useState<Job | null>(null);
  const [adding, setAdding] = useState(false);
  const [scheduling, setScheduling] = useState<Job | null>(null);
  const [confirming, setConfirming] = useState<ShiftOccurrence | null>(null);
  const [payingCheque, setPayingCheque] = useState<Paycheque | null>(null);
  const [recordingPay, setRecordingPay] = useState(false);

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
        <ShiftList shifts={shifts} onConfirm={setConfirming} busy={loading} />
      )}

      {jobs.length > 0 && (
        <PaychequeList
          paycheques={paycheques}
          onAdd={() => { setPayingCheque(null); setRecordingPay(true); }}
          onEdit={(cheque) => { setPayingCheque(cheque); setRecordingPay(true); }}
          busy={loading}
        />
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
    </div>
  );
}
