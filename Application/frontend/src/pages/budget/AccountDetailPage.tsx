import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AccountBalanceChart from "../../features/budget/components/AccountBalanceChart";
import AccountFlowChart from "../../features/budget/components/AccountFlowChart";
import DeleteConfirmModal from "../../features/grades/components/DeleteConfirmModal";
import EditTransactionModal from "../../features/budget/components/EditTransactionModal";
import TuitionModal from "../../features/budget/components/TuitionModal";
import ProgressBar from "../../features/budget/components/ProgressBar";
import RecordSpendModal from "../../features/budget/components/RecordSpendModal";
import Transactions from "../../features/budget/components/Transactions";
import WhereItWent from "../../features/budget/components/WhereItWent";
import { useAccountActivity } from "../../features/budget/hooks/useAccountActivity";
import { useCourses } from "../../features/grades/hooks/useCourses";
import { fetchAccounts } from "../../features/budget/api";
import { useTransactionDelete } from "../../features/budget/hooks/useTransactionDelete";
import { formatMoney } from "../../features/budget/money";
import { Account, Transaction } from "../../features/budget/types";
import { useAuth } from "../../app/auth/AuthContext";
import "../../styles/budget.css";
import "../../styles/budget/accountDetail.css";

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
              <span className="accountBalance">{formatMoney(activity.balance)}</span>
              <span className="small-text muted accountBalanceNote">balance today</span>
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

            <input
              className="loginInput monthPicker"
              type="month"
              value={month.slice(0, 7)}
              onChange={(event) => setMonth(`${event.target.value}-01`)}
              aria-label="Month to show"
            />
            </div>
          </div>

          {/* The month's figures beside the month's shape: four tiles in a 2x2
              block, with the daily flow they summarise next to them rather than
              a screen below. Every figure here is for the chosen month, so each
              tile says so rather than leaving the reader to assume. */}
          <div className="accountSplit">
            <ul className="tileRow">
              <Tile label={`In · ${label}`} value={formatMoney(activity.total_in)} tone="in" />
              <Tile label={`Out · ${label}`} value={formatMoney(activity.total_out)} tone="out" />
              <Tile
                label={`Net · ${label}`}
                value={formatMoney(activity.net, { signed: true })}
                tone={activity.net < 0 ? "out" : "in"}
              />
              <Tile label={`Movements · ${label}`} value={String(activity.transaction_count)} />
            </ul>

            <AccountFlowChart days={activity.daily} monthLabel={label} />
          </div>

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

          {/* Below the target bar, the same split again: what the month went on
              under the tiles, and the longer balance history under the chart it
              continues. With no categories recorded there is nothing to put in
              the left column, so the history takes the full width rather than
              sitting beside a gap. */}
          {activity.by_category.length > 0 ? (
            <div className="accountSplit">
              <WhereItWent entries={activity.by_category} />
              <AccountBalanceChart points={activity.balance_history} />
            </div>
          ) : (
            <AccountBalanceChart points={activity.balance_history} />
          )}

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
        </>
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

interface TileProps {
  readonly label: string;
  readonly value: string;
  readonly tone?: "in" | "out";
}

function Tile({ label, value, tone }: TileProps) {
  return (
    <li className="tile">
      <span className="small-text muted tileLabel">{label}</span>
      <span className={tone ? `tileValue tileValue--${tone}` : "tileValue"}>{value}</span>
    </li>
  );
}

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
