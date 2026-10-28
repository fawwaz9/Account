import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AccountBalanceChart from "../../features/budget/components/AccountBalanceChart";
import AccountFlowChart from "../../features/budget/components/AccountFlowChart";
import DeleteConfirmModal from "../../features/grades/components/DeleteConfirmModal";
import EditTransactionModal from "../../features/budget/components/EditTransactionModal";
import InvestmentReturnPanel from "../../features/budget/components/InvestmentReturnPanel";
import TuitionModal from "../../features/budget/components/TuitionModal";
import ProgressBar from "../../features/budget/components/ProgressBar";
import RecordSpendModal from "../../features/budget/components/RecordSpendModal";
import ImportModal from "../../features/budget/components/ImportModal";
import AccountImports from "../../features/budget/components/AccountImports";
import Transactions from "../../features/budget/components/Transactions";
import WhereItWent from "../../features/budget/components/WhereItWent";
import { useAccountActivity } from "../../features/budget/hooks/useAccountActivity";
import { useCourses } from "../../features/grades/hooks/useCourses";
import { fetchAccounts, setAccountCategoryLimit } from "../../features/budget/api";
import { useTransactionDelete } from "../../features/budget/hooks/useTransactionDelete";
import { formatMoney } from "../../features/budget/money";
import { returnTile } from "../../features/budget/returnTile";
import { Account, Transaction } from "../../features/budget/types";
import { useAuth } from "../../app/auth/AuthContext";
import "../../styles/budget.css";
import "../../styles/budget/accountDetail.css";

/**
 * One account's page: worth or balance, the month's tiles, charts, ledger, limits and imports.
 * Tuition rows open the tuition editor; other rows the plain one.
 */
export default function AccountDetailPage() {
  const { accountId } = useParams<{ accountId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { courses } = useCourses();
  const [editingTuition, setEditingTuition] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);

  // Only the tuition editor's "paid from" select needs the full account
  // list, so it is fetched when one is opened rather than on every visit.
  useEffect(() => {
    if (!user || editingTuition === null) return;
    let cancelled = false;
    fetchAccounts(user.id)
      .then((rows) => { if (!cancelled) setAccounts(rows); })
      .catch(() => { if (!cancelled) setAccounts([]); });
    return () => { cancelled = true; };
  }, [user, editingTuition]);

  // A tuition row's amount is derived from its per-credit rate, so it opens the
  // tuition editor. The plain one refuses that edit, by design.
  function editTransaction(transaction: Transaction) {
    if (transaction.tuition_payment_id) {
      setEditingTuition(transaction.tuition_payment_id);
      return;
    }
    setEditing(transaction);
  }
  const { activity, transactions, categories, month, setMonth, loading, error, reload } =
    useAccountActivity(accountId);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [recording, setRecording] = useState(false);
  const [importing, setImporting] = useState(false);
  // Bumped after an import, so the imports list reads again alongside the page.
  const [importNonce, setImportNonce] = useState(0);

  /**
   * This account's limit for one category, or null to remove it.
   *
   * Reloads the whole page rather than just the list, because a limit also
   * moves the Planned spend figure above it -- that target is the sum of these
   * when there are any.
   */
  async function handleSetLimit(
    categoryId: string,
    limit: number | null,
    thisMonthOnly: boolean,
  ) {
    if (!user || !accountId) return;
    // The month on screen when overriding, and null for the standing figure --
    // which is what carries into every month that was never overridden.
    await setAccountCategoryLimit(
      user.id, accountId, categoryId, limit, thisMonthOnly ? month : null,
    );
    await reload();
  }
  const remove = useTransactionDelete(reload);

  const label = monthLabel(month);

  return (
    <div className="container accountPage">
      <button
        type="button"
        className="backButton"
        onClick={() => navigate(-1)}
        aria-label="Back"
      >
        &larr;
      </button>

      {loading && !activity && <p className="muted">Loading that account...</p>}
      {error && <p className="muted">{error}</p>}

      {activity && (
        <>
          <div className="accountHeader">
            <div>
              <h1 className="accountName">{activity.account_name}</h1>
              {/* On an investment account the headline is what the holding is
                  worth, matching its card. The ledger balance moves to the note
                  under it rather than disappearing -- it is what the percentage
                  is measured against, and it is still the honest answer to "how
                  much have I put in".

                  Built from `all_time_return`, never the month's reading: this
                  figure is all-time, and using the month's would add March's gain
                  to today's balance as soon as the month picker stepped back. */}
              <span className="accountBalance">
                {formatMoney(
                  activity.all_time_return
                    ? activity.balance + activity.all_time_return.difference_amount
                    : activity.balance,
                )}
              </span>
              <span className="small-text muted accountBalanceNote">
                {activity.all_time_return
                  ? `worth today · ${formatMoney(activity.balance)} paid in`
                  : "balance today"}
              </span>
            </div>

            {/* Next to the month rather than down with the ledger: this is the
                one thing you come to an account's page to *do*, and the figures
                above it are what it changes. */}
            <div className="accountHeaderActions">
              <button
                type="button"
                className="buttons addCourseButton"
                onClick={() => setRecording(true)}
              >
                Record spending
              </button>
              <button
                type="button"
                className="calButton"
                onClick={() => setImporting(true)}
              >
                Import CSV
              </button>

            <input
              className="loginInput monthPicker"
              type="month"
              value={month.slice(0, 7)}
              onChange={(event) => setMonth(`${event.target.value}-01`)}
              aria-label="Month to show"
            />
            </div>
          </div>

          {/* The month in four figures, across the full width. They are the
              headline of the page and read as one row of "this month"; every
              one is for the chosen month, so each tile says so rather than
              leaving the reader to assume. */}
          <ul className="tileRow">
            <Tile label={`In · ${label}`} value={formatMoney(activity.total_in)} tone="in" />
            <Tile label={`Out · ${label}`} value={formatMoney(activity.total_out)} tone="out" />
            <Tile
              label={`Net · ${label}`}
              value={formatMoney(activity.net, { signed: true })}
              tone={activity.net < 0 ? "out" : "in"}
            />
            {/* An investment account's fourth tile is its return, not its
                movement count. Counting deposits says nothing about whether the
                holding grew, which is the question the account exists to answer.
                Every other kind of account keeps Movements. */}
            {activity.kind === "investment" ? (
              <Tile {...returnTile(activity, label)} />
            ) : (
              <Tile label={`Movements · ${label}`} value={String(activity.transaction_count)} />
            )}
          </ul>

          {activity.kind === "investment" && (
            <InvestmentReturnPanel
              accountId={activity.account_id}
              month={month}
              figure={activity.investment_return}
              ledgerAtMonth={activity.ledger_balance_at_month}
              onSaved={reload}
            />
          )}

          <section className="accountTarget">
            <div className="sectionHeading">
              <h2>Planned spend</h2>
              <span className="small-text muted">
                {activity.planned === 0
                  ? "No target set for this month"
                  : `${formatMoney(activity.total_out)} of ${formatMoney(activity.planned)}`}
              </span>
            </div>

            <ProgressBar
              value={activity.total_out}
              max={activity.planned}
              percent={activity.used_percent}
              label={`${activity.account_name} spend against target`}
            />

            <span className="small-text muted">
              {targetNote(activity.planned, activity.remaining)}
            </span>
          </section>

          {/* What the month went on, beside the two readings of the same
              money: the daily in-and-out first, because it is the month the
              figures above describe, and the long balance history under it as
              the wider context that flow sits inside.

              "Where it went" is always rendered, where it used to appear only
              once something had been spent. Category limits are set from inside
              it, so hiding it on an empty month hid the only way to budget an
              account nobody has used yet -- the same reasoning that made the
              budget page's copy unconditional. */}
          <div className="accountSplit">
            <WhereItWent entries={activity.by_category} onSetLimit={handleSetLimit} />

            <div className="accountCharts">
              <AccountFlowChart days={activity.daily} monthLabel={label} />
              <AccountBalanceChart points={activity.balance_history} />
            </div>
          </div>

          <section className="ledgerSection">
            <div className="sectionHeading">
              <h2>{label}</h2>
            </div>

            {remove.error && <p className="muted">{remove.error}</p>}

            <Transactions
              transactions={transactions}
              accounts={activity ? [{ id: activity.account_id, name: activity.account_name }] : []}
              onDelete={remove.requestDelete}
              onEdit={editTransaction}
              deletingId={remove.deletingId}
              emptyMessage={`Nothing moved through this account in ${label}.`}
            />
          </section>

          {user && accountId && (
            <AccountImports
              userId={user.id}
              accountId={accountId}
              nonce={importNonce}
              onUndone={reload}
            />
          )}
        </>
      )}

      {importing && user && accountId && activity && (
        <ImportModal
          userId={user.id}
          accountId={accountId}
          accountName={activity.account_name}
          onClose={() => setImporting(false)}
          onImported={() => {
            setImportNonce((n) => n + 1);
            void reload();
          }}
        />
      )}

      <DeleteConfirmModal
        open={remove.pending !== null}
        title="Remove which part?"
        message={
          remove.pending
            ? `"${remove.pending.description || "This deposit"}" was split across ` +
              `${remove.pending.group_size} accounts. Remove only this account's ` +
              `share, or the whole deposit?`
            : ""
        }
        confirmLabel="Whole deposit"
        secondaryAction={{ label: "Just this share", onConfirm: remove.deleteRow }}
        onConfirm={remove.deleteGroup}
        onCancel={remove.cancel}
        submitting={remove.deletingId !== null}
        error={remove.error}
      />

      <TuitionModal


        open={editingTuition !== null}


        accounts={accounts}


        paymentId={editingTuition}


        onClose={() => setEditingTuition(null)}


        onSaved={reload}


      />


      <EditTransactionModal
        transaction={editing}
        categories={categories}
        courses={courses}
        onClose={() => setEditing(null)}
        onSaved={reload}
      />

      {/* `activity` is what carries the account's name, so this is mounted only
          once the page has it -- and by then `accountId` is certainly a string,
          which is why the non-null assertion is safe rather than hopeful. */}
      {activity && (
        <RecordSpendModal
          open={recording}
          accountId={accountId!}
          accountName={activity.account_name}
          categories={categories}
          courses={courses}
          onClose={() => setRecording(false)}
          onSaved={reload}
        />
      )}
    </div>
  );
}

/** Props for a summary tile. */
interface TileProps {
  readonly label: string;
  readonly value: string;
  /** Colours the value as money in or out. */
  readonly tone?: "in" | "out";
}

/** One summary tile: a label over a value. */
function Tile({ label, value, tone }: TileProps) {
  return (
    <li className="tile">
      <span className="small-text muted tileLabel">{label}</span>
      <span className={tone ? `tileValue tileValue--${tone}` : "tileValue"}>{value}</span>
    </li>
  );
}

/** What the target tile says: no target, over, or left. */
function targetNote(planned: number, remaining: number) {
  if (planned === 0) return "Set a target on the budget page to track this account.";
  if (remaining < 0) return `${formatMoney(-remaining)} over`;
  return `${formatMoney(remaining)} left`;
}

/** "September 2026" from a YYYY-MM-01 key. */
function monthLabel(month: string) {
  const [year, index] = month.split("-").map(Number);
  return new Date(year, index - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}
