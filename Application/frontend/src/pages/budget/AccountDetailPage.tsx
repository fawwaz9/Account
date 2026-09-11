import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AccountBalanceChart from "../../features/budget/components/AccountBalanceChart";
import AccountFlowChart from "../../features/budget/components/AccountFlowChart";
import DeleteConfirmModal from "../../features/grades/components/DeleteConfirmModal";
import EditTransactionModal from "../../features/budget/components/EditTransactionModal";
import ProgressBar from "../../features/budget/components/ProgressBar";
import Transactions from "../../features/budget/components/Transactions";
import WhereItWent from "../../features/budget/components/WhereItWent";
import { useAccountActivity } from "../../features/budget/hooks/useAccountActivity";
import { useTransactionDelete } from "../../features/budget/hooks/useTransactionDelete";
import { formatMoney } from "../../features/budget/money";
import { Transaction } from "../../features/budget/types";
import { useAuth } from "../../app/auth/AuthContext";
import "../../styles/budget.css";
import "../../styles/budget/accountDetail.css";

export default function AccountDetailPage() {
  const { accountId } = useParams<{ accountId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { activity, transactions, categories, month, setMonth, loading, error, reload } =
    useAccountActivity(accountId);
  const [editing, setEditing] = useState<Transaction | null>(null);
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

            <input
              className="loginInput monthPicker"
              type="month"
              value={month.slice(0, 7)}
              onChange={(event) => setMonth(`${event.target.value}-01`)}
              aria-label="Month to show"
            />
          </div>

          {/* Every figure below the header is for the chosen month, so each
              tile says so rather than leaving the reader to assume. */}
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
              label={`${activity.account_name} spend against target`}
            />

            <span className="small-text muted">
              {targetNote(activity.planned, activity.remaining)}
            </span>
          </section>

          <AccountBalanceChart points={activity.balance_history} />

          {activity.by_category.length > 0 && (
            <WhereItWent entries={activity.by_category} />
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
              onEdit={setEditing}
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

      <EditTransactionModal
        transaction={editing}
        categories={categories}
        onClose={() => setEditing(null)}
        onSaved={reload}
      />
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
