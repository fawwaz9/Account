import { useState } from "react";
import SafeToSpend from "./SafeToSpend";
import CashFlowForecast from "./CashFlowForecast";
import NetWorth from "./NetWorth";
import SinkingFunds from "./SinkingFunds";
import Subscriptions from "./Subscriptions";
import SinkingFundModal from "./SinkingFundModal";
import Sectors, { positionChanges } from "./Sectors";
import Transactions from "./Transactions";
import AddMoneyModal from "./AddMoneyModal";
import PlannedSpend from "./PlannedSpend";
import WhereItWent from "./WhereItWent";
import IncomeSplitModal from "./IncomeSplitModal";
import CategoriesModal from "./CategoriesModal";
import EditTransactionModal from "./EditTransactionModal";
import EditAccountModal from "./EditAccountModal";
import Recurring from "./Recurring";
import RecurringModal from "./RecurringModal";
import { useBudget } from "../hooks/useBudget";
import { useCourses } from "../../grades/hooks/useCourses";
import TuitionModal from "./TuitionModal";
import TermBudget from "./TermBudget";
import { useTransactionDelete } from "../hooks/useTransactionDelete";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import { deleteRecurring, setBudgetTarget, updateAccount } from "../api";
import { Account, RecurringTransaction, Transaction } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { useShortcut } from "../../../shared/hooks/useShortcut";

const NO_ACCOUNTS_YET = "Add an account first -- money has to go somewhere.";

export default function BudgetView() {
  const { user } = useAuth();
  const {
    accounts, transactions, categories, summary, recurring, upcoming,
    safe, worth, month, setMonth, loading, summaryLoading, error, reload,
  } = useBudget();
  // Reused rather than refetched: the course picker needs the same list the
  // Grades page already loads.
  const { courses } = useCourses();
  const [modalOpen, setModalOpen] = useState(false);

  // One PATCH per account that moved. Separate requests, so a failure midway
  // leaves a mixed order -- which costs nothing but order, and is fixed by
  // dragging again. Reloaded either way, so the grid shows what was saved.
  async function reorderAccounts(orderedIds: string[]) {
    if (!user) return;
    try {
      for (const change of positionChanges(accounts, orderedIds)) {
        await updateAccount(user.id, change.id, { position: change.position });
      }
    } finally {
      await reload();
    }
  }
  // Record Money, under the same condition its button is enabled on.
  useShortcut("n", () => setModalOpen(true), accounts.length > 0);
  const [tuitionOpen, setTuitionOpen] = useState(false);
  const [editingTuition, setEditingTuition] = useState<string | null>(null);
  // Bumped alongside reload so the term panel refetches when money moves.
  const [termNonce, setTermNonce] = useState(0);
  const reloadAll = () => { reload(); setTermNonce((n) => n + 1); };

  // A tuition row's amount is derived from its per-credit rate, so it goes to
  // the tuition editor rather than the plain one -- which would change the
  // ledger and leave the course pages saying something else.
  function editTransaction(transaction: Transaction) {
    if (transaction.tuition_payment_id) {
      setEditingTuition(transaction.tuition_payment_id);
      return;
    }
    setEditing(transaction);
  }
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [addingAccount, setAddingAccount] = useState(false);
  const [splitOpen, setSplitOpen] = useState(false);
  const [categoriesOpen, setCategoriesOpen] = useState(false);
  // "Stop" deletes the instruction. The payments it already made are real money
  // that really moved, so those stay -- but the rule itself does not come back.
  const [stoppingRule, setStoppingRule] = useState<RecurringTransaction | null>(null);
  const [fundOpen, setFundOpen] = useState(false);
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
    setStoppingRule(null);

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
        {/* A disabled control with no reason on it is a dead end. Both of
            these need somewhere for the money to go, so they say so. */}
        <button
          type="button"
          className="buttons addCourseButton"
          onClick={() => setModalOpen(true)}
          disabled={accounts.length === 0}
          title={accounts.length === 0 ? NO_ACCOUNTS_YET : undefined}
        >
          Record Money
        </button>
        {/* Its own action rather than a fifth tab in Record Money: tuition
            happens twice a year and is shaped nothing like the other four. */}
        <button
          type="button"
          className="buttons addCourseButton"
          onClick={() => setTuitionOpen(true)}
          disabled={accounts.length === 0}
          title={accounts.length === 0 ? NO_ACCOUNTS_YET : undefined}
        >
          Pay Tuition
        </button>
      </div>

      {loading && <p className="muted">Loading your accounts...</p>}
      {error && <p className="muted" role="alert">{error}</p>}
      {!loading && !error && accounts.length === 0 && (
        <p className="muted">
          {NO_ACCOUNTS_YET}{" "}
          <button
            type="button"
            className="linkButton"
            onClick={() => setAddingAccount(true)}
          >
            Add one
          </button>
        </p>
      )}

      {!loading && !error && (
        <>
          {/* First, because these are the only things on this page that answer
              a question rather than recording one. Everything below is the
              working; this is the conclusion -- what you can spend now, and
              where you stand overall. */}
          <div className="budgetTopRow">
            <SafeToSpend safe={safe} />
            <NetWorth figure={worth} />
          </div>

          {/* Under the answers for now, because this is the answer for the
              term: where the spending accounts are heading, and when. */}
          <CashFlowForecast nonce={termNonce} />

          <Sectors
            accounts={accounts}
            onReorder={reorderAccounts}
            onEdit={setEditingAccount}
            onAdd={() => setAddingAccount(true)}
          />

          {/* Under the accounts, above the month: what is reserved is a claim on
              the balances just shown, and it changes the safe figure at the top. */}
          <SinkingFunds
            nonce={termNonce}
            onAdd={() => setFundOpen(true)}
            onChanged={reload}
          />

          {/* Above the monthly view on purpose: the month is the wrong unit for
              tuition and textbooks, so the term is the frame you want first. */}
          <TermBudget nonce={termNonce} />

          <div className="budgetGrid">
            <div className="budgetColumn">
              <PlannedSpend
                summary={summary}
                month={month}
                onMonthChange={setMonth}
                onSetTarget={handleSetTarget}
                pending={summaryLoading}
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
                  onEdit={editTransaction}
                  deletingId={remove.deletingId}
                  emptyMessage="Nothing recorded today or yesterday."
                />
              </section>
            </div>

            <WhereItWent
              entries={spendByCategory}
              onEditSplit={() => setSplitOpen(true)}
              onEditCategories={() => setCategoriesOpen(true)}
              pending={summaryLoading}
            />
          </div>

          {/* Above Recurring: a finding here is what turns into one of the rules
              listed below it, so the case comes before the list it feeds. */}
          <Subscriptions nonce={termNonce} onConfirmed={reloadAll} />

          <Recurring
            rules={recurring}
            upcoming={upcoming}
            onAdd={() => { setEditingRule(null); setAddingRule(true); }}
            onEdit={(rule) => { setEditingRule(rule); setAddingRule(true); }}
            onDelete={setStoppingRule}
            busy={ruleBusy}
          />
        </>
      )}

      <DeleteConfirmModal
        open={stoppingRule !== null}
        title="Stop this standing instruction?"
        message={
          stoppingRule
            ? `"${stoppingRule.description}" will stop running and the rule will be ` +
              `deleted. Payments it has already made stay in the ledger — that money ` +
              `really moved.`
            : ""
        }
        confirmLabel="Stop it"
        submitting={ruleBusy}
        onCancel={() => setStoppingRule(null)}
        onConfirm={() => { if (stoppingRule) void handleStopRule(stoppingRule); }}
      />

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
      <SinkingFundModal
        open={fundOpen}
        accounts={accounts}
        onClose={() => setFundOpen(false)}
        onSaved={reload}
      />


      <EditAccountModal
        account={editingAccount}
        accounts={accounts}
        onClose={() => setEditingAccount(null)}
        onSaved={reloadAll}
      />

      <IncomeSplitModal
        open={splitOpen}
        accounts={accounts}
        onClose={() => setSplitOpen(false)}
        onSaved={reloadAll}
      />

      <CategoriesModal
        open={categoriesOpen}
        categories={categories}
        onClose={() => setCategoriesOpen(false)}
        onSaved={reloadAll}
      />

      {addingAccount && (
        <EditAccountModal
          account={null}
          creating
          accounts={accounts}
          onClose={() => setAddingAccount(false)}
          onSaved={reloadAll}
        />
      )}

      <EditTransactionModal
        transaction={editing}
        categories={categories}
        courses={courses}
        onClose={() => setEditing(null)}
        onSaved={reloadAll}
      />

      <RecurringModal
        open={addingRule}
        rule={editingRule}
        accounts={accounts}
        categories={categories}
        onClose={() => { setAddingRule(false); setEditingRule(null); }}
        onSaved={reloadAll}
      />

      <AddMoneyModal
        open={modalOpen}
        accounts={accounts}
        categories={categories}
        courses={courses}
        onClose={() => setModalOpen(false)}
        onSaved={reloadAll}
      />

      <TuitionModal
        open={tuitionOpen}
        accounts={accounts}
        onClose={() => setTuitionOpen(false)}
        onSaved={reloadAll}
      />

      <TuitionModal
        open={editingTuition !== null}
        accounts={accounts}
        paymentId={editingTuition}
        onClose={() => setEditingTuition(null)}
        onSaved={reloadAll}
      />
    </div>
  );
}
