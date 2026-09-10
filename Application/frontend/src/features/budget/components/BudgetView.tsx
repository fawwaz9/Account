import { useMemo, useState } from "react";
import Sectors from "./Sectors";
import Transactions from "./Transactions";
import AddMoneyModal from "./AddMoneyModal";
import PlannedSpend from "./PlannedSpend";
import EditTransactionModal from "./EditTransactionModal";
import EditAccountModal from "./EditAccountModal";
import { useBudget } from "../hooks/useBudget";
import { deleteTransaction, setBudgetTarget } from "../api";
import { Account, Transaction } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

export default function BudgetView() {
  const { user } = useAuth();
  const { accounts, transactions, categories, summary, month, setMonth, loading, error, reload } =
    useBudget();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);

  const visible = useMemo(
    () =>
      selectedId === null
        ? transactions
        : transactions.filter((transaction) => transaction.account_id === selectedId),
    [transactions, selectedId]
  );

  async function handleDelete(transaction: Transaction) {
    if (!user) return;

    setDeletingId(transaction.id);
    setDeleteError(null);
    try {
      await deleteTransaction(user.id, transaction.id);
      // Balances are derived, so the accounts have to be re-read too.
      await reload();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Could not delete that");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleSetTarget(accountId: string, planned: number) {
    if (!user) return;
    await setBudgetTarget(user.id, accountId, month, planned);
    await reload();
  }

  const selectedName = accounts.find((account) => account.id === selectedId)?.name;

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
          <Sectors
            accounts={accounts}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onEdit={setEditingAccount}
          />

          <PlannedSpend
            summary={summary}
            month={month}
            onMonthChange={setMonth}
            onSetTarget={handleSetTarget}
          />

          <section className="ledgerSection">
            <div className="sectionHeading">
              <h2>{selectedName ? `${selectedName} activity` : "Recent activity"}</h2>
              {selectedId && (
                <button
                  type="button"
                  className="buttons addCourseButton"
                  onClick={() => setSelectedId(null)}
                >
                  All accounts
                </button>
              )}
            </div>

            {deleteError && <p className="muted">{deleteError}</p>}

            <Transactions
              transactions={visible}
              accounts={accounts}
              onDelete={handleDelete}
              onEdit={setEditing}
              deletingId={deletingId}
            />
          </section>
        </>
      )}

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
