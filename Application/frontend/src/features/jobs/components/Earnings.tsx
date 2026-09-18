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
 * The headline on each window is what was PAID, net. Earned sits with the
 * hours that produced it on the line below, because those two come from the
 * same place. Note that the two are not a sum and a remainder: earned counts
 * shifts falling inside the window, while paid counts cheques DATED inside it,
 * and a cheque arriving this week usually pays for last fortnight. They are
 * two accounts of different work, deliberately side by side.
 */
export default function Earnings({ earnings }: EarningsProps) {
  if (!earnings) return null;

  const windows = [earnings.week, earnings.month, earnings.term].filter(
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

      {earnings.upcoming.length > 0 && <Owed rows={earnings.upcoming} />}
    </section>
  );
}

function WindowCard({ window }: { readonly window: EarningsWindow }) {
  const assumed = window.per_job.reduce((total, job) => total + job.assumed_count, 0);

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

      {/* The shifts story, grouped: hours, what they were worth, and the tips
          that never pass through a cheque. */}
      <span className="small-text muted">
        {hours(window.counted_minutes)} worked
        {` · ${formatMoney(window.gross_earned)} earned`}
        {window.cash_tips > 0 && ` · ${formatMoney(window.cash_tips)} cash tips`}
      </span>

      {/* The cheque story, under it. The gap between this and earned above is
          the point of the page: a fortnight worked that nobody has paid for. */}
      {window.gross_paid > 0 && (
        <span className="small-text muted earnPaid">
          {formatMoney(window.gross_paid)} gross, {formatMoney(window.deducted)} deducted
        </span>
      )}

      {assumed > 0 && (
        <span className="small-text earnAssumed">
          {assumed} {assumed === 1 ? "shift" : "shifts"} still unconfirmed
        </span>
      )}

      {window.per_job.length > 1 && (
        <ul className="earnPerJob">
          {window.per_job.map((job) => (
            <li key={job.job_id}>
              <span>{job.job_name}</span>
              <span>{formatMoney(job.gross_earned)}</span>
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

function Owed({ rows }: { readonly rows: UpcomingPay[] }) {
  const owed = rows.filter((row) => row.unpaid_minutes > 0 || row.next_pay_on);
  if (owed.length === 0) return null;

  return (
    <div className="earnOwed">
      <span className="small-text muted earnLabel">Not paid yet</span>
      <ul className="earnOwedList">
        {owed.map((row) => (
          <li key={row.job_id}>
            <span>{row.job_name}</span>
            <span className="small-text muted">
              {row.unpaid_minutes > 0 ? hours(row.unpaid_minutes) : "nothing outstanding"}
              {row.unpaid_estimate !== null && row.unpaid_estimate > 0 &&
                ` · about ${formatMoney(row.unpaid_estimate)}`}
              {row.next_pay_on && ` · next cheque ${dueLabel(row.next_pay_on)}`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function hours(minutes: number): string {
  return `${Math.round((minutes / 60) * 10) / 10}h`;
}

function share(part: number, total: number): number {
  return total === 0 ? 0 : (part / total) * 100;
}
