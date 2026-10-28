import { Job, JOB_KIND_LABELS, JobKind } from "../types";
import { formatMoney } from "../../budget/money";
import { dueLabel } from "../../../shared/utils/dateUtils";

/** Props for a job card. */
interface JobCardProps {
  readonly job: Job;
  /** Minutes of shifts in the next three weeks, despite the name. */
  readonly hours: number;
  readonly onEdit: (job: Job) => void;
  readonly onSchedule: (job: Job) => void;
  readonly busy: boolean;
}

/** One job: its kind, its pay in the terms that kind makes true, hours ahead and next cheque. */
export default function JobCard({ job, hours, onEdit, onSchedule, busy }: JobCardProps) {
  return (
    <li className={`jobCard${job.is_current ? "" : " jobCardEnded"}`}>
      <div className="jobCardHead">
        <div>
          <h3 className="jobName">{job.name}</h3>
          {job.employer && <span className="small-text muted">{job.employer}</span>}
        </div>
        <span className={`jobKind jobKind-${job.kind}`}>{JOB_KIND_LABELS[job.kind]}</span>
      </div>

      <p className="jobPay">{payLine(job)}</p>

      <div className="jobMeta">
        <span className="small-text muted">
          {hours > 0 ? `${trimHours(hours)}h in the next three weeks` : "No shifts scheduled"}
        </span>
        {job.next_pay_on && (
          <span className="small-text muted">Next cheque {dueLabel(job.next_pay_on)}</span>
        )}
        {!job.is_current && <span className="jobEnded">Ended</span>}
      </div>

      <div className="jobActions">
        <button type="button" className="jobButton" onClick={() => onSchedule(job)} disabled={busy}>
          Shifts
        </button>
        <button type="button" className="jobButton" onClick={() => onEdit(job)} disabled={busy}>
          Edit
        </button>
      </div>
    </li>
  );
}

/** The pay line: hourly rate, amount per pay period, or billed per invoice. */
function payLine(job: Job): string {
  if (job.kind === JobKind.HOURLY && job.hourly_rate !== null) {
    return `${formatMoney(job.hourly_rate)} an hour`;
  }
  if (job.kind === JobKind.SALARIED && job.period_amount !== null) {
    return `${formatMoney(job.period_amount)} a pay period`;
  }
  return "Billed per invoice";
}

/** Minutes as hours to one decimal, without a trailing ".0". */
function trimHours(minutes: number): string {
  return String(Math.round((minutes / 60) * 10) / 10);
}
