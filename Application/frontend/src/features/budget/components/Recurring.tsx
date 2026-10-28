import { RecurringTransaction, UpcomingCharge } from "../types";
import { formatMoney } from "../money";
import HelpTip from "../../../shared/components/HelpTip";
import { dueLabel, shortDate } from "../../../shared/utils/dateUtils";

/** Display label per standing-instruction kind. */
const KIND_LABELS: Record<string, string> = {
  expense: "Expense",
  income: "Income",
  transfer: "Transfer",
  deposit: "Deposit",
};

/** A rule in words, e.g. "every 2 weeks, until Mar 3"; weekdays are not spelled out. */
function ruleInWords(rule: RecurringTransaction): string {
  const { freq, interval } = rule.recurrence;
  const unit = freq === "daily" ? "day" : freq === "weekly" ? "week" : "month";
  const every = interval === 1 ? `every ${unit}` : `every ${interval} ${unit}s`;

  if (rule.recurrence.until) return `${every}, until ${shortDate(rule.recurrence.until)}`;
  if (rule.recurrence.count) return `${every}, ${rule.recurrence.count} times`;
  return every;
}

/** Props for the standing-instructions panel. */
interface RecurringProps {
  readonly rules: RecurringTransaction[];
  readonly upcoming: UpcomingCharge[];
  readonly onAdd: () => void;
  readonly onEdit: (rule: RecurringTransaction) => void;
  /** Ask to stop a rule; the page confirms first. */
  readonly onDelete: (rule: RecurringTransaction) => void;
  readonly busy: boolean;
  /** Accounts left out of counted figures: their charges stay listed, out of the totals. */
  readonly uncounted?: ReadonlySet<string>;
}

/**
 * Standing instructions beside what they commit you to next.
 * The upcoming strip is projections, never ledger rows; its totals skip uncounted accounts.
 */
export default function Recurring({
  rules,
  upcoming,
  onAdd,
  onEdit,
  onDelete,
  busy,
  uncounted,
}: RecurringProps) {
  // The totals are an analytic, so an unticked account's charges leave them;
  // the list below still shows every rule, since the rules are records.
  const counted = upcoming.filter((charge) => !(charge.account_id && uncounted?.has(charge.account_id)));
  const committed = counted.reduce((total, charge) => total + charge.signed_amount, 0);
  const leaving = counted
    .filter((charge) => charge.signed_amount < 0)
    .reduce((total, charge) => total + charge.signed_amount, 0);

  return (
    <section className="recurringSection">
      <div className="recurringSplit">
        <div>
          <div className="sectionHeading">
            <h2>Standing instructions</h2>
            <HelpTip label="What a standing instruction is">
              Rent, a subscription or a monthly transfer, recorded for you on the day it
              happens rather than waiting to be typed. Stopping one deletes the rule; the
              payments it already made stay in the ledger.
            </HelpTip>
            <button type="button" className="calButton" onClick={onAdd} disabled={busy}>
              Add
            </button>
          </div>

          {rules.length === 0 ? (
            <p className="muted">Nothing recurring yet.</p>
          ) : (
            <ul className="recurringList">
              {rules.map((rule) => (
                <li
                  key={rule.id}
                  className={rule.active ? "recurringRow" : "recurringRow recurringRowPaused"}
                >
                  <div className="recurringBody">
                    <p className="recurringTitle">
                      {rule.description || KIND_LABELS[rule.kind] || rule.kind}
                      {!rule.active && <span className="recurringPaused"> · paused</span>}
                    </p>
                    <p className="recurringMeta">
                      <span className={`recurringKind recurringKind-${rule.kind}`}>
                        {KIND_LABELS[rule.kind] ?? rule.kind}
                      </span>
                      <span>{ruleInWords(rule)}</span>
                      {rule.active && rule.next_due_on && (
                        <span className="recurringNext">next {dueLabel(rule.next_due_on)}</span>
                      )}
                      {rule.last_run_on && (
                        <span className="muted">last {shortDate(rule.last_run_on)}</span>
                      )}
                    </p>
                  </div>

                  <span className="recurringAmount">{formatMoney(rule.amount)}</span>

                  <div className="recurringActions">
                    <button
                      type="button"
                      className="calButton"
                      onClick={() => onEdit(rule)}
                      disabled={busy}
                      aria-label={`Edit ${rule.description || rule.kind}`}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="calButton calButtonDanger"
                      onClick={() => onDelete(rule)}
                      disabled={busy}
                      aria-label={`Stop ${rule.description || rule.kind}`}
                    >
                      Stop
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {upcoming.length > 0 && (
          <div className="upcomingBlock">
            <div className="sectionHeading">
              <h3>Coming up</h3>
              {/* Money leaving is the number that governs what you can actually
                  spend, so it leads; the net is beside it for the full picture. */}
              <span className="upcomingTotal">
                {formatMoney(Math.abs(leaving))} out
                {committed !== leaving && ` · ${formatMoney(committed, { signed: true })} net`}
              </span>
            </div>

            <ul className="upcomingList">
              {upcoming.slice(0, 8).map((charge) => (
                <li key={`${charge.recurring_id}-${charge.on_date}`} className="upcomingRow">
                  <span className="upcomingWhen">{dueLabel(charge.on_date)}</span>
                  <span className="upcomingWhat">
                    {charge.description || KIND_LABELS[charge.kind] || charge.kind}
                    {charge.account_name && <span className="muted"> · {charge.account_name}</span>}
                  </span>
                  <span
                    className={
                      charge.signed_amount < 0 ? "upcomingAmount upcomingOut" : "upcomingAmount"
                    }
                  >
                    {formatMoney(charge.signed_amount, { signed: true })}
                  </span>
                </li>
              ))}
            </ul>

            <p className="calHint">
              Not recorded yet — these have not moved any money, so they are not in your balances.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
