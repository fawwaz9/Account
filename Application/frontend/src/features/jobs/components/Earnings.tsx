import {
  EarningsSummary,
  EarningsWindow,
  EffectiveRate,
  HoursAgainstClasses,
  UpcomingPay,
} from "../types";
import { formatMoney } from "../../budget/money";
import { dueLabel } from "../../../shared/utils/dateUtils";

/** Props: the earnings summary, or null while loading. */
interface EarningsProps {
  readonly earnings: EarningsSummary | null;
}

/**
 * What the jobs came to: money paid in cards, everything the shifts predict under Estimates.
 * Earned and paid are never added: they count different work in the same window.
 */
export default function Earnings({ earnings }: EarningsProps) {
  if (!earnings) return null;

  // Month and term only. Pay does not arrive weekly, so a weekly pay figure was
  // a number nobody could act on. `earnings.week` is still computed and still
  // on the wire -- it is the window that test_earnings.py makes thirteen
  // assertions through, where a fixed seven days makes the expected shift
  // counts obvious -- it is simply not drawn.
  const windows = [earnings.month, earnings.term].filter(
    (window): window is EarningsWindow => window !== null
  );

  // Nothing worked and nothing paid, so every figure would be zero.
  const empty = windows.every((w) => w.counted_minutes === 0 && w.gross_paid === 0);
  if (empty) return null;

  return (
    <section className="earnSection" aria-label="Earnings">
      <div className="earnWindows">
        {windows.map((window) => (
          <WindowCard key={window.label} window={window} />
        ))}
      </div>

      <div className="earnRow">
        <RateCard rate={earnings.effective_rate} />
        {earnings.this_week && <CommitmentCard week={earnings.this_week} />}
      </div>

      <Estimates windows={windows} rows={earnings.upcoming} />
    </section>
  );
}

/** One window's money that arrived: net paid, its gross and deductions, and which jobs paid. */
function WindowCard({ window }: { readonly window: EarningsWindow }) {
  // Jobs that were actually paid in this window. Filtering on the paid figure
  // rather than on `per_job.length` matters now that the rows show pay: the
  // list also carries jobs that only worked, and a breakdown of the paid total
  // that lists jobs paid nothing does not explain the number above it.
  const paid = window.per_job.filter((job) => job.net_paid > 0);

  return (
    <div className="earnCard">
      <span className="small-text muted earnLabel">{window.label}</span>
      {/* What the bank actually saw. A window with work in it but no cheque
          yet says so in words rather than showing a confident $0.00, which
          would read as "you earned nothing" in exactly the case this page
          exists to surface. Same treatment as the rate card. */}
      {window.gross_paid > 0 ? (
        <span className="earnHeadline">{formatMoney(window.net_paid)}</span>
      ) : (
        <span className="earnHeadline earnHeadlineEmpty">Nothing paid yet</span>
      )}

      {window.gross_paid > 0 && (
        <span className="small-text muted earnPaid">
          {formatMoney(window.gross_paid)} gross, {formatMoney(window.deducted)} deducted
        </span>
      )}

      {/* Which jobs the headline came from. Only worth drawing when more than
          one job paid, since one job's breakdown is the headline again. */}
      {paid.length > 1 && (
        <ul className="earnPerJob">
          {paid.map((job) => (
            <li key={job.job_id}>
              <span>{job.job_name}</span>
              <span>{formatMoney(job.net_paid)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Net and gross pay per hour actually paid; says so when nothing is paid yet. */
function RateCard({ rate }: { readonly rate: EffectiveRate }) {
  if (rate.net_per_hour === null) {
    return (
      <div className="earnCard">
        <span className="small-text muted earnLabel">Effective rate</span>
        <span className="earnHeadline earnHeadlineEmpty">Nothing paid yet</span>
        <span className="small-text muted">
          Record a cheque with its pay period and this fills in.
        </span>
      </div>
    );
  }

  return (
    <div className="earnCard">
      <span className="small-text muted earnLabel">Effective rate</span>
      <span className="earnHeadline">{formatMoney(rate.net_per_hour)}<span className="earnPer">/h</span></span>
      <span className="small-text muted">
        {formatMoney(rate.gross_per_hour ?? 0)}/h before {rate.deduction_percent}% comes off
      </span>
      <span className="small-text muted">over {hours(rate.paid_minutes)} paid</span>
    </div>
  );
}

/** This week's hours of work beside classes and tasks. */
function CommitmentCard({ week }: { readonly week: HoursAgainstClasses }) {
  const total = week.work_minutes + week.class_minutes + week.task_minutes;
  if (total === 0) return null;

  return (
    <div className="earnCard">
      <span className="small-text muted earnLabel">This week</span>
      <span className="earnHeadline">{hours(total)}<span className="earnPer"> committed</span></span>

      <div className="earnBar" role="img" aria-label={
        `${hours(week.class_minutes)} of classes, ${hours(week.work_minutes)} of work, ` +
        `${hours(week.task_minutes)} estimated against tasks`
      }>
        <span className="earnBarClass" style={{ width: `${share(week.class_minutes, total)}%` }} />
        <span className="earnBarWork" style={{ width: `${share(week.work_minutes, total)}%` }} />
        <span className="earnBarTask" style={{ width: `${share(week.task_minutes, total)}%` }} />
      </div>

      <span className="small-text muted">
        {hours(week.class_minutes)} classes · {hours(week.work_minutes)} work
        {week.task_minutes > 0 && ` · ${hours(week.task_minutes)} tasks`}
      </span>
    </div>
  );
}

/** Props for the estimates block. */
interface EstimatesProps {
  readonly windows: EarningsWindow[];
  readonly rows: UpcomingPay[];
}

/**
 * Everything the shifts predict: per job, unpaid hours, their likely worth and the next cheque.
 * Unconfirmed shifts are counted per window, since month and term overlap.
 */
function Estimates({ windows, rows }: EstimatesProps) {
  const owed = rows.filter((row) => row.unpaid_minutes > 0 || row.next_pay_on);
  const worked = windows.filter(
    (window) => window.counted_minutes > 0 || window.gross_earned > 0
  );
  if (owed.length === 0 && worked.length === 0) return null;

  return (
    <div className="earnOwed">
      <span className="small-text muted earnLabel">Estimates</span>

      {worked.length > 0 && (
        <ul className="earnOwedList">
          {worked.map((window) => {
            const assumed = window.per_job.reduce(
              (total, job) => total + job.assumed_count, 0
            );
            return (
              <li key={window.label}>
                <span>{window.label}</span>
                <span className="small-text muted">
                  {hours(window.counted_minutes)} worked
                  {` · ${formatMoney(window.gross_earned)} earned`}
                  {window.cash_tips > 0 && ` · ${formatMoney(window.cash_tips)} cash tips`}
                  {assumed > 0 &&
                    ` · ${assumed} ${assumed === 1 ? "shift" : "shifts"} unconfirmed`}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {owed.length > 0 && (
        <ul className="earnOwedList">
          {owed.map((row) => (
            <li key={row.job_id}>
              <span>{row.job_name}</span>
              <span className="small-text muted">
                {row.unpaid_minutes > 0
                  ? `${hours(row.unpaid_minutes)} unpaid`
                  : "nothing outstanding"}
                {row.unpaid_estimate !== null && row.unpaid_estimate > 0 &&
                  ` · about ${formatMoney(row.unpaid_estimate)}`}
                {row.next_pay_on && ` · next cheque ${dueLabel(row.next_pay_on)}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Minutes as hours to one decimal, e.g. "7.5h". */
function hours(minutes: number): string {
  return `${Math.round((minutes / 60) * 10) / 10}h`;
}

/** Part of total as a percent; 0 when the total is 0. */
function share(part: number, total: number): number {
  return total === 0 ? 0 : (part / total) * 100;
}
