import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import HelpTip from "../../../shared/components/HelpTip";
import { deletePaycheque, previewPaycheque, recordPaycheque, updatePaycheque } from "../api";
import {
  DeductionEntry,
  Job,
  Paycheque,
  PaychequeCreate,
  PaychequePreview,
} from "../types";
import { formatMoney } from "../../budget/money";
import { useAuth } from "../../../app/auth/AuthContext";
import { today } from "../../../shared/utils/dateUtils";

/** Props for the paycheque dialog. */
interface PaychequeModalProps {
  readonly open: boolean;
  readonly jobs: Job[];
  /** The cheque to edit, or null to record a new one. */
  readonly paycheque: Paycheque | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/** A new cheque for the first job, dated today, with nothing filled in. */
function blank(jobs: Job[]): PaychequeCreate {
  return {
    job_id: jobs[0]?.id ?? "",
    occurred_on: today(),
    gross_amount: 0,
    period_start: null,
    period_end: null,
    deductions: [],
    allocations: [],
    notes: null,
  };
}

/** Form values from a cheque, or a blank one; allocations always start empty. */
function formFor(paycheque: Paycheque | null, jobs: Job[]): PaychequeCreate {
  if (!paycheque) return blank(jobs);
  return {
    job_id: paycheque.job_id,
    occurred_on: paycheque.occurred_on,
    gross_amount: paycheque.gross_amount,
    period_start: paycheque.period_start,
    period_end: paycheque.period_end,
    deductions: paycheque.deductions.map((d) => ({
      description: d.description,
      amount: d.amount,
    })),
    allocations: [],
    notes: paycheque.notes,
  };
}

/**
 * Record or edit a paycheque: gross, deductions and pay period, previewed against the shifts.
 * Only the net reaches the ledger, split by income share; deleting confirms first.
 */
export default function PaychequeModal({
  open,
  jobs,
  paycheque,
  onClose,
  onSaved,
}: PaychequeModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<PaychequeCreate>(formFor(paycheque, jobs));
  const [preview, setPreview] = useState<PaychequePreview | null>(null);
  const [saving, setSaving] = useState(false);
  // Permanent, and it takes the cheque's deduction lines with it.
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(formFor(paycheque, jobs));
    setPreview(null);
    setError(null);
  }, [paycheque, open, jobs]);

  // What the hours say it should be, fetched once both ends of the period are
  // set. Only a prediction: the cheque is whatever actually arrived.
  useEffect(() => {
    if (!user || !open || !form.job_id || !form.period_start || !form.period_end) {
      setPreview(null);
      return;
    }

    let cancelled = false;
    previewPaycheque(user.id, form.job_id, form.period_start, form.period_end)
      .then((next) => { if (!cancelled) setPreview(next); })
      .catch(() => { if (!cancelled) setPreview(null); });

    return () => { cancelled = true; };
  }, [user, open, form.job_id, form.period_start, form.period_end]);

  if (!open) return null;

  function update<K extends keyof PaychequeCreate>(key: K, value: PaychequeCreate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function patchDeduction(index: number, change: Partial<DeductionEntry>) {
    setForm((current) => ({
      ...current,
      deductions: current.deductions.map((entry, at) =>
        at === index ? { ...entry, ...change } : entry
      ),
    }));
  }

  const deducted = form.deductions.reduce((total, entry) => total + (entry.amount || 0), 0);
  const net = Math.round((form.gross_amount - deducted) * 100) / 100;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSaving(true);
    setError(null);
    try {
      // Rows with nothing typed in them are unused slots, not errors.
      const payload = {
        ...form,
        deductions: form.deductions.filter((d) => d.description.trim() && d.amount > 0),
      };
      if (paycheque) {
        const { job_id: _ignored, ...rest } = payload;
        await updatePaycheque(user.id, paycheque.id, rest);
      } else {
        await recordPaycheque(user.id, payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that cheque");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setConfirmingDelete(false);
    if (!user || !paycheque) return;
    setSaving(true);
    try {
      await deletePaycheque(user.id, paycheque.id);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove that cheque");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title={paycheque ? "Edit paycheque" : "Record a paycheque"}
      onClose={onClose}
      panelClassName="widePopup"
    >
      <form className="calForm" onSubmit={handleSubmit}>
        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Job</span>
            <select
              className="calInput"
              value={form.job_id}
              onChange={(e) => update("job_id", e.target.value)}
              disabled={paycheque !== null}
              required
            >
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>{job.name}</option>
              ))}
            </select>
          </label>

          <label className="calField">
            <span className="calFieldLabel">Paid on</span>
            <input
              type="date"
              className="calInput"
              value={form.occurred_on}
              onChange={(e) => update("occurred_on", e.target.value)}
              required
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Gross</span>
            <input
              type="number"
              min={0}
              step="any"
              className="calInput"
              value={form.gross_amount || ""}
              onChange={(e) => update("gross_amount", Number(e.target.value) || 0)}
              placeholder="612.00"
              required
            />
          </label>
        </div>

        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Period from</span>
            <input
              type="date"
              className="calInput"
              value={form.period_start ?? ""}
              onChange={(e) => update("period_start", e.target.value || null)}
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Period to</span>
            <input
              type="date"
              className="calInput"
              value={form.period_end ?? ""}
              onChange={(e) => update("period_end", e.target.value || null)}
            />
          </label>
        </div>

        {preview && <PreviewLine preview={preview} gross={form.gross_amount} />}

        <fieldset className="payDeductions">
          <legend className="calFieldLabel">Deductions</legend>
          <HelpTip label="What deductions are">
            Tax, EI, CPP, dues. These never reach the ledger — only the net does, so
            your balance moves by what actually landed in the account.
          </HelpTip>

          {form.deductions.map((entry, index) => (
            <div className="calRow" key={index}>
              <input
                className="calInput"
                value={entry.description}
                onChange={(e) => patchDeduction(index, { description: e.target.value })}
                placeholder="Income tax"
              />
              <input
                type="number"
                min={0}
                step="any"
                className="calInput taskInputNarrow"
                value={entry.amount || ""}
                onChange={(e) => patchDeduction(index, { amount: Number(e.target.value) || 0 })}
                placeholder="73.44"
              />
              <button
                type="button"
                className="calButton calButtonDanger"
                onClick={() => update("deductions", form.deductions.filter((_, at) => at !== index))}
              >
                Remove
              </button>
            </div>
          ))}

          <button
            type="button"
            className="calButton"
            onClick={() => update("deductions", [...form.deductions, { description: "", amount: 0 }])}
          >
            Add a deduction
          </button>
        </fieldset>

        <p className="payNet">
          Net to your accounts: <strong>{formatMoney(net)}</strong>
          <span className="small-text muted"> · split by income share</span>
        </p>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          {paycheque && (
            <button
              type="button"
              className="calButton calButtonDanger"
              onClick={() => setConfirmingDelete(true)}
              disabled={saving}
            >
              Remove
            </button>
          )}
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving || net <= 0}>
            {saving ? "Saving…" : "Record cheque"}
          </button>
        </div>
      </form>

      <DeleteConfirmModal
        open={confirmingDelete}
        title="Delete this paycheque?"
        message={
          "The cheque and its deduction lines will be deleted. The shifts it was " +
          "calculated from stay where they are — what goes is the record of being paid."
        }
        submitting={saving}
        error={error}
        onCancel={() => setConfirmingDelete(false)}
        onConfirm={() => void handleDelete()}
      />
    </Modal>
  );
}

/** What the period's shifts predict beside the gross typed: short, over or matching. */
function PreviewLine({ preview, gross }: { readonly preview: PaychequePreview; readonly gross: number }) {
  if (preview.expected_gross === null) {
    return (
      <p className="small-text muted">
        {preview.shift_count} shifts, {hours(preview.counted_minutes)} in this period.
        Contract work is billed per invoice, so there is nothing to compare against.
      </p>
    );
  }

  const variance = Math.round((gross - preview.expected_gross) * 100) / 100;
  const short = gross > 0 && variance < -0.01;

  return (
    <p className={`payPreview${short ? " payPreviewShort" : ""}`}>
      <span>
        {preview.shift_count} shifts · {hours(preview.counted_minutes)} ·
        expected {formatMoney(preview.expected_gross)}
      </span>
      {gross > 0 && (
        <span className="small-text">
          {short
            ? ` — ${formatMoney(-variance)} short`
            : variance > 0.01
              ? ` — ${formatMoney(variance)} over`
              : " — matches"}
        </span>
      )}
      {preview.assumed_count > 0 && (
        <span className="small-text muted">
          {" "}({preview.assumed_count} of those shifts still unconfirmed)
        </span>
      )}
    </p>
  );
}

/** Minutes as hours to one decimal, e.g. "7.5h". */
function hours(minutes: number): string {
  return `${Math.round((minutes / 60) * 10) / 10}h`;
}
