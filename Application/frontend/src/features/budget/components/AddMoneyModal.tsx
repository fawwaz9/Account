import { useEffect, useState } from "react";
import { createTransaction, createTransfer, previewDeposit, recordDeposit } from "../api";
import { useDebounce } from "../../../shared/hooks/useDebounce";
import { Account, DepositAllocation, SpendCategory } from "../types";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";

interface AddMoneyModalProps {
  readonly open: boolean;
  readonly accounts: readonly Account[];
  readonly categories: readonly SpendCategory[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

type Mode = "expense" | "income" | "transfer" | "deposit";

const today = () => new Date().toISOString().slice(0, 10);

export default function AddMoneyModal({
  open,
  accounts,
  categories,
  onClose,
  onSaved,
}: AddMoneyModalProps) {
  const { user } = useAuth();
  const [mode, setMode] = useState<Mode>("expense");
  const [accountId, setAccountId] = useState("");
  const [toAccountId, setToAccountId] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [occurredOn, setOccurredOn] = useState(today());
  const [categoryId, setCategoryId] = useState("");
  const [allocations, setAllocations] = useState<DepositAllocation[]>([]);
  const [needsShares, setNeedsShares] = useState(false);
  const debouncedAmount = useDebounce(amount, 300);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Default the pickers once accounts arrive, and reset on each open so a
  // previous entry never carries over into a new one.
  useEffect(() => {
    if (!open || accounts.length === 0) return;
    setAccountId(accounts[0].id);
    setToAccountId(accounts[1]?.id ?? accounts[0].id);
    setAmount("");
    setDescription("");
    setOccurredOn(today());
    setCategoryId("");
    setAllocations([]);
    setError(null);
  }, [open, accounts]);

  // Ask the server how the deposit would divide, so the preview and what gets
  // written can never round differently.
  useEffect(() => {
    if (!open || mode !== "deposit" || !user) return;

    const value = Number(debouncedAmount);
    if (!value || value <= 0) {
      setAllocations([]);
      return;
    }

    let cancelled = false;
    previewDeposit(user.id, value)
      .then((preview) => {
        if (cancelled) return;
        setAllocations(preview.allocations);
        setNeedsShares(preview.needs_shares);
      })
      .catch(() => {
        if (!cancelled) setAllocations([]);
      });

    return () => {
      cancelled = true;
    };
  }, [open, mode, debouncedAmount, user]);

  if (!open) return null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSubmitting(true);
    setError(null);

    try {
      if (mode === "deposit") {
        await recordDeposit(user.id, {
          amount: Number(amount),
          occurred_on: occurredOn,
          description: description || null,
          allocations,
        });
      } else if (mode === "transfer") {
        await createTransfer(user.id, {
          from_account_id: accountId,
          to_account_id: toAccountId,
          amount: Number(amount),
          description: description || null,
          occurred_on: occurredOn,
          // Only expenses carry a category; the server ignores it on income.
          category_id: mode === "expense" && categoryId ? categoryId : null,
        });
      } else {
        await createTransaction(user.id, {
          kind: mode,
          account_id: accountId,
          amount: Number(amount),
          description: description || null,
          occurred_on: occurredOn,
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="popup">
      <div className="addCoursePopup">
        <h2>Record Money</h2>

        <div className="moneyTabs">
          {(["expense", "income", "transfer", "deposit"] as Mode[]).map((option) => (
            <button
              type="button"
              key={option}
              className={mode === option ? "moneyTab moneyTabActive" : "moneyTab"}
              onClick={() => {
                setMode(option);
                setError(null);
              }}
            >
              {option}
            </button>
          ))}
        </div>

        <form className="loginForm" onSubmit={handleSubmit}>
          {mode !== "deposit" && (
          <div className="loginField">
            <label htmlFor="money-account">
              {mode === "transfer" ? "From" : "Account"}
            </label>
            <select
              id="money-account"
              className="loginInput"
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.name}</option>
              ))}
            </select>
          </div>
          )}

          {mode === "transfer" && (
            <div className="loginField">
              <label htmlFor="money-to">To</label>
              <select
                id="money-to"
                className="loginInput"
                value={toAccountId}
                onChange={(event) => setToAccountId(event.target.value)}
              >
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="loginField">
            <label htmlFor="money-amount">Amount</label>
            <input
              id="money-amount"
              className="loginInput"
              type="number"
              min={0.01}
              step="0.01"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              required
            />
          </div>

          {mode === "deposit" && (
            <div className="depositSplit">
              <span className="depositSplitTitle">Split across accounts</span>
              {needsShares && (
                <p className="small-text muted">
                  No account has an income share yet. Set one on each account, or
                  type the amounts below.
                </p>
              )}
              {allocations.map((allocation) => {
                const account = accounts.find((item) => item.id === allocation.account_id);
                return (
                  <div className="depositRow" key={allocation.account_id}>
                    <span className="depositRowName">{account?.name ?? "Account"}</span>
                    <input
                      className="loginInput depositRowInput"
                      type="number"
                      min={0}
                      step="0.01"
                      value={allocation.amount}
                      aria-label={`Amount for ${account?.name ?? "account"}`}
                      onChange={(event) =>
                        setAllocations((current) =>
                          current.map((entry) =>
                            entry.account_id === allocation.account_id
                              ? { ...entry, amount: Number(event.target.value) }
                              : entry
                          )
                        )
                      }
                    />
                  </div>
                );
              })}
              {allocations.length > 0 && (
                <span className="small-text muted depositSum">
                  Allocated{" "}
                  {allocations.reduce((sum, entry) => sum + entry.amount, 0).toFixed(2)} of{" "}
                  {(Number(amount) || 0).toFixed(2)}
                </span>
              )}
            </div>
          )}

          {mode === "expense" && categories.length > 0 && (
            <div className="loginField">
              <label htmlFor="money-category">Category</label>
              <select
                id="money-category"
                className="loginInput"
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
              >
                <option value="">Uncategorised</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="loginField">
            <label htmlFor="money-description">Description</label>
            <input
              id="money-description"
              className="loginInput"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={mode === "transfer" ? "Optional" : "e.g. Groceries"}
            />
          </div>

          <div className="loginField">
            <label htmlFor="money-date">Date</label>
            <input
              id="money-date"
              className="loginInput"
              type="date"
              value={occurredOn}
              onChange={(event) => setOccurredOn(event.target.value)}
              required
            />
          </div>

          {error && <p className="loginError">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200"
              disabled={submitting}
            >
              Cancel
            </button>
            <button type="submit" className="loginSubmit" disabled={submitting}>
              {submitting ? "Saving..." : "Record"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
