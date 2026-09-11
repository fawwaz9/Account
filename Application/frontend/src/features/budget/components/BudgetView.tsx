import { useState } from "react";
import Sectors from "./Sectors";
import Transactions from "./Transactions";
import AddMoneyModal from "./AddMoneyModal";
import PlannedSpend from "./PlannedSpend";
import WhereItWent from "./WhereItWent";
import EditTransactionModal from "./EditTransactionModal";
import EditAccountModal from "./EditAccountModal";
import Recurring from "./Recurring";
import RecurringModal from "./RecurringModal";
import { useBudget } from "../hooks/useBudget";
import { useTransactionDelete } from "../hooks/useTransactionDelete";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import { deleteRecurring, setBudgetTarget } from "../api";
import { Account, RecurringTransaction, Transaction } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

export default function BudgetView() {
  const { user } = useAuth();
  const {
    accounts, transactions, categories, summary, recurring, upcoming,
    month, setMonth, loading, error, reload,
  } = useBudget();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [editingRule, setEditingRule] = useState<RecurringTransaction | null>(null);
  const [addingRule, setAddingRule] = useState(false);
  const [ruleBusy, setRuleBusy] = useState(false);
  const remove = useTransactionDelete(reload);

  async function handleSetTarget(accountId: string, planned: number) {
    if (!user) return;
    await setBudgetTarget(user.id, accountId, month, planned);
    await reload();
  }

  async function handleStopRule(rule: RecurringTransaction) {
    if (!user) return;

    setRuleBusy(true);
    try {
      // Stops the instruction only. The payments it already made are real money
      // that really moved, so they stay in the ledger.
      await deleteRecurring(user.id, rule.id);
      await reload();
    } finally {
      setRuleBusy(false);
    }
  }

  const spendByCategory = summary?.by_category ?? [];

  return (
    <div className="container budgetPage">
      <div className="budgetHeader">
        <h1 className="gradesTitle">Budget</h1>
        <button
          type="button"
          className="buttons addCourseButton"
          onClick={() => setModalOpen(true)}
          disabled={accounts.length === 0}
        >
          Record Money
        </button>
      </div>

      {loading && <p className="muted">Loading your accounts...</p>}
      {error && <p className="muted">{error}</p>}

      {!loading && !error && (
        <>
          <Sectors accounts={accounts} onEdit={setEditingAccount} />

          <div className={spendByCategory.length > 0 ? "budgetGrid" : ""}>
            <div className="budgetColumn">
              <PlannedSpend
                summary={summary}
                month={month}
                onMonthChange={setMonth}
                onSetTarget={handleSetTarget}
              />

              <section className="ledgerSection">
                <div className="sectionHeading">
                  <h2>Recent activity</h2>
                </div>

                {remove.error && <p className="muted">{remove.error}</p>}

                <Transactions
                  transactions={transactions}
                  accounts={accounts}
                  onDelete={remove.requestDelete}
                  onEdit={setEditing}
                  deletingId={remove.deletingId}
                  emptyMessage="Nothing recorded today or yesterday."
                />
              </section>
            </div>

            {spendByCategory.length > 0 && <WhereItWent entries={spendByCategory} />}
          </div>

          <Recurring
            rules={recurring}
            upcoming={upcoming}
            onAdd={() => { setEditingRule(null); setAddingRule(true); }}
            onEdit={(rule) => { setEditingRule(rule); setAddingRule(true); }}
            onDelete={handleStopRule}
            busy={ruleBusy}
          />
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

      <EditAccountModal
        account={editingAccount}
        accounts={accounts}
        onClose={() => setEditingAccount(null)}
        onSaved={reload}
      />

      <EditTransactionModal
        transaction={editing}
        categories={categories}
        onClose={() => setEditing(null)}
        onSaved={reload}
      />

      <RecurringModal
        open={addingRule}
        rule={editingRule}
        accounts={accounts}
        categories={categories}
        onClose={() => { setAddingRule(false); setEditingRule(null); }}
        onSaved={reload}
      />

      <AddMoneyModal
        open={modalOpen}
        accounts={accounts}
        categories={categories}
        onClose={() => setModalOpen(false)}
        onSaved={reload}
      />
    </div>
  );
}
