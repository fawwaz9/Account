import { useEffect, useRef, useState } from "react";
import { fetchTuitionPreview, recordTuition } from "../api";
import { Account, TuitionDeduction, TuitionPreview } from "../types";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";
import { useDebounce } from "../../../shared/hooks/useDebounce";
import { formatMoney } from "../money";
import { localToday } from "../dates";
import Modal from "../../../shared/components/Modal";

interface TuitionModalProps {
  readonly open: boolean;
  readonly accounts: readonly Account[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

const BLANK: TuitionDeduction = { description: "", amount: 0 };

/**
 * Paying tuition, which is not shaped like any other payment.
 *
 * A bill is a rate times a number of credits, plus fees that belong to no
 * course, less deductions that never touched the account. What leaves the
 * account is the net, and that is the single line the ledger gets. What each
 * course is worth is the gross, and that is what the course pages report.
 *
 * The form shows both totals on purpose. They are different numbers answering
 * different questions, and showing only one would imply they are the same.
 */
export default function TuitionModal({ open, accounts, onClose, onSaved }: TuitionModalProps) {
  const { user } = useAuth();
  const [accountId, setAccountId] = useState("");
  const [occurredOn, setOccurredOn] = useState(localToday());
  const [costPerCredit, setCostPerCredit] = useState("");
  const [fees, setFees] = useState("");
  const [description, setDescription] = useState("");
  const [deductions, setDeductions] = useState<TuitionDeduction[]>([]);
  const [preview, setPreview] = useState<TuitionPreview | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deductionsTotal = deductions.reduce(
    (total, entry) => total + (Number(entry.amount) || 0), 0
  );
  const debouncedRate = useDebounce(costPerCredit, 300);
  const debouncedFees = useDebounce(fees, 300);
  const debouncedDeductions = useDebounce(String(deductionsTotal), 300);
  // The preview is cheap but not instant, and the inputs change faster than it
  // returns; an older answer landing last would show a total for figures that
  // are no longer on screen.
  const latestRequest = useRef(0);

  useEffect(() => {
    if (!open) return;
    setAccountId(accounts[0]?.id ?? "");
    setOccurredOn(localToday());
    setCostPerCredit("");
    setFees("");
    setDescription("");
    setDeductions([]);
    setError(null);
  }, [open, accounts]);

  useEffect(() => {
    if (!open || !user) return;
    const ticket = ++latestRequest.current;
    let cancelled = false;

    fetchTuitionPreview(
      user.id,
      Number(debouncedRate) || 0,
      Number(debouncedFees) || 0,
      Number(debouncedDeductions) || 0
    )
      .then((result) => {
        if (!cancelled && ticket === latestRequest.current) setPreview(result);
      })
      .catch(() => {
        if (!cancelled && ticket === latestRequest.current) setPreview(null);
      });

    return () => { cancelled = true; };
  }, [open, user, debouncedRate, debouncedFees, debouncedDeductions]);

  function updateDeduction(index: number, patch: Partial<TuitionDeduction>) {
    setDeductions((current) =>
      current.map((entry, at) => (at === index ? { ...entry, ...patch } : entry))
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSubmitting(true);
    setError(null);
    try {
      await recordTuition(user.id, {
        account_id: accountId,
        occurred_on: occurredOn,
        cost_per_credit: Number(costPerCredit) || 0,
        fees: Number(fees) || 0,
        description: description || null,
        // Blank rows are scaffolding, not deductions.
        deductions: deductions
          .filter((entry) => entry.description.trim() && Number(entry.amount) > 0)
          .map((entry) => ({
            description: entry.description.trim(),
            amount: Number(entry.amount),
          })),
      });
      onSaved();
      onClose();
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  // Built on the server: school_year is a year of standing, not a calendar
  // year, so joining the parts here produced "3 Fall".
  const term = preview?.term_name ?? "your current term";
  const blocked = Boolean(preview && !preview.can_record);

  return (
    <Modal title="Pay Tuition" onClose={onClose} panelClassName="widePopup">
      <form className="loginForm" onSubmit={handleSubmit}>
        <div className="calRow">
          <div className="loginField calField">
            <label htmlFor="tuition-account">Paid from</label>
            <select
              id="tuition-account"
              className="loginInput"
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
              required
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.name}</option>
              ))}
            </select>
          </div>

          <div className="loginField calField">
            <label htmlFor="tuition-date">Date</label>
            <input
              id="tuition-date"
              className="loginInput"
              type="date"
              value={occurredOn}
              onChange={(event) => setOccurredOn(event.target.value)}
              required
            />
          </div>

          <div className="loginField calField">
            <label htmlFor="tuition-rate">Cost per credit</label>
            <input
              id="tuition-rate"
              className="loginInput"
              type="number"
              step="any"
              min={0}
              value={costPerCredit}
              onChange={(event) => setCostPerCredit(event.target.value)}
              placeholder="e.g. 250"
            />
          </div>
        </div>

        {/* Instalments add their rates together, so a second payment needs half
            the rate rather than the whole of it again. Said out loud, because
            silently doubling every course's cost is the obvious trap here. */}
        {preview && preview.already_recorded_per_credit > 0 && (
          <p className="tuitionNote">
            {formatMoney(preview.already_recorded_per_credit)} per credit is already
            recorded for {term}. Rates add up, so enter only this instalment's share.
          </p>
        )}

        <div className="tuitionCourses">
          <div className="tuitionCoursesHead">
            <span>{term} — transfer credits excluded</span>
            <strong>{preview?.credits_counted ?? 0} credits</strong>
          </div>
          {preview?.courses.length ? (
            <ul className="tuitionCourseList">
              {preview.courses.map((course) => (
                <li key={course.course_id}>
                  <span>{course.code}</span>
                  <span className="tuitionCourseCredits">{course.credits} cr</span>
                  <span>{formatMoney(course.share)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="tuitionEmpty">
              No courses in {term}. Add them, or set your term in Settings.
            </p>
          )}
        </div>

        <div className="calRow">
          <div className="loginField calField">
            <label htmlFor="tuition-fees">Fees (not tied to any course)</label>
            <input
              id="tuition-fees"
              className="loginInput"
              type="number"
              step="any"
              min={0}
              value={fees}
              onChange={(event) => setFees(event.target.value)}
              placeholder="e.g. 310"
            />
          </div>

          <div className="loginField calField">
            <label htmlFor="tuition-description">Description</label>
            <input
              id="tuition-description"
              className="loginInput"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={`Tuition ${term}`}
            />
          </div>
        </div>

        <div className="tuitionDeductions">
          <div className="tuitionCoursesHead">
            <span>Deductions — money that lowered the bill without entering your account</span>
          </div>
          {deductions.map((entry, index) => (
            <div className="calRow" key={index}>
              <div className="loginField calField">
                <input
                  className="loginInput"
                  value={entry.description}
                  onChange={(event) => updateDeduction(index, { description: event.target.value })}
                  placeholder="e.g. Entrance scholarship"
                  aria-label={`Deduction ${index + 1} description`}
                />
              </div>
              <div className="loginField calField">
                <input
                  className="loginInput"
                  type="number"
                  step="any"
                  min={0}
                  value={entry.amount || ""}
                  onChange={(event) => updateDeduction(index, { amount: Number(event.target.value) })}
                  placeholder="Amount"
                  aria-label={`Deduction ${index + 1} amount`}
                />
              </div>
              <button
                type="button"
                className="bulkRemove"
                onClick={() => setDeductions((current) => current.filter((_, at) => at !== index))}
                aria-label={`Remove deduction ${index + 1}`}
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            className="bulkAddRow"
            onClick={() => setDeductions((current) => [...current, { ...BLANK }])}
          >
            + Add a deduction
          </button>
        </div>

        {preview && (
          <div className="tuitionTotals">
            <div className="tuitionLine">
              <span>{preview.credits_counted} credits × {formatMoney(preview.cost_per_credit)}</span>
              <span>{formatMoney(preview.gross)}</span>
            </div>
            <div className="tuitionLine">
              <span>Fees</span>
              <span>{formatMoney(preview.fees)}</span>
            </div>
            {preview.deductions_total > 0 && (
              <div className="tuitionLine tuitionLineMinus">
                <span>Deductions</span>
                <span>−{formatMoney(preview.deductions_total)}</span>
              </div>
            )}
            <div className="tuitionLine tuitionLinePayable">
              <span>Leaves your account</span>
              <strong>{formatMoney(preview.payable)}</strong>
            </div>
            {/* The asymmetry is the design, so it is stated rather than hidden:
                a scholarship lowers what you pay, not what a course is worth. */}
            {preview.gross > 0 && preview.deductions_total > 0 && (
              <p className="tuitionNote">
                Course pages will still show {formatMoney(preview.gross)} across{" "}
                {preview.courses.length} courses — deductions lower what you pay, not
                what a course is worth.
              </p>
            )}
          </div>
        )}

        {blocked && <p className="error">{preview?.reason}</p>}
        {error && <p className="error">{error}</p>}

        <div className="calActions">
          <button type="button" className="buttons" onClick={onClose}>Cancel</button>
          <button
            type="submit"
            className="buttons !bg-gold"
            disabled={submitting || blocked || !accountId}
          >
            {submitting ? "Recording…" : "Record payment"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
