import {
  EarningsSummary,
  EarningsWindow,
  EffectiveRate,
  HoursAgainstClasses,
  UpcomingPay,
} from "../types";
import { formatMoney } from "../../budget/money";
import { dueLabel } from "../../../shared/utils/dateUtils";

interface EarningsProps {
  readonly earnings: EarningsSummary | null;
}

/**
 * What the jobs came to.
 *
 * Earned and paid are shown apart throughout, because they answer different
 * questions: earned comes from the shifts and is a prediction, paid comes from
 * cheques that arrived. One combined figure would hide the thing this page
 * exists to surface -- a fortnight worked that nobody has paid for yet.
 *
 * So the split is by source, not by window. The cards at the top are money
 * that arrived -- net paid, the gross and deduction behind it, and which jobs
 * it came from. Everything the shifts merely predict lives under Estimates.
 *
 * The two are not a sum and a remainder, and separating them makes that easier
 * to forget rather than harder: earned counts shifts falling INSIDE a window,
 * paid counts cheques DATED inside it, and a cheque arriving this week usually
 * pays for last fortnight. They are two accounts of different work.
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

/**
 * Work beside classes for the current week.
 *
 * The one figure here that is not about money: forty hours of commitment is
 * worth seeing whoever it is owed to.
 */
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

interface EstimatesProps {
  readonly windows: EarningsWindow[];
  readonly rows: UpcomingPay[];
}

/**
 * Everything the shifts say, in one place.
 *
 * This was "Not paid yet" and already was an estimates section in substance --
 * per job, the hours no cheque has covered since the last period closed, what
 * they are probably worth, and when the next cheque is due. The figures the
 * window cards used to carry moved in beside it when those cards became purely
 * about money that arrived.
 *
 * Folded into the existing block rather than added as a third one: two headings
 * both answering "what do the shifts say", differing only by window, is two
 * places to look for one answer.
 *
 * Every figure here is a projection. The unconfirmed count is said per window
 * rather than totalled, because month and term overlap and adding them would
 * count the same unconfirmed shift twice.
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

function hours(minutes: number): string {
  return `${Math.round((minutes / 60) * 10) / 10}h`;
}

function share(part: number, total: number): number {
  return total === 0 ? 0 : (part / total) * 100;
}
