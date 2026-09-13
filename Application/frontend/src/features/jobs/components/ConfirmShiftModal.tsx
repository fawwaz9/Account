import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { recordShift } from "../api";
import { ShiftOccurrence, ShiftRecordUpsert } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

interface ConfirmShiftModalProps {
  readonly shift: ShiftOccurrence | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/** HH:MM, since <input type="time"> shows nothing for HH:MM:SS. */
function clockValue(value: string | null): string {
  return value ? value.slice(0, 5) : "";
}

function formFor(shift: ShiftOccurrence | null): ShiftRecordUpsert {
  return {
    // Pre-filled from the schedule, so confirming an ordinary shift is one
    // click and only an unusual one needs typing.
    worked_start: shift ? clockValue(shift.worked_start ?? shift.scheduled_start) : null,
    worked_end: shift ? clockValue(shift.worked_end ?? shift.scheduled_end) : null,
    confirmed: true,
    tip_amount: shift?.tip_amount ?? 0,
    tip_is_cash: shift?.tip_is_cash ?? true,
    rate_override: shift?.rate_override ?? null,
    notes: shift?.notes ?? null,
  };
}

export default function ConfirmShiftModal({ shift, onClose, onSaved }: ConfirmShiftModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<ShiftRecordUpsert>(formFor(shift));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(formFor(shift));
    setError(null);
  }, [shift]);

  if (!shift) return null;

  function update<K extends keyof ShiftRecordUpsert>(key: K, value: ShiftRecordUpsert[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || !shift) return;

    setSaving(true);
    setError(null);
    try {
      await recordShift(user.id, shift.event_id, shift.on_date, form);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`${shift.job_name} · ${shift.on_date}`} onClose={onClose}>
      <form className="calForm" onSubmit={handleSubmit}>
        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Started</span>
            <input
              type="time"
              className="calInput"
              value={form.worked_start ?? ""}
              onChange={(e) => update("worked_start", e.target.value || null)}
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Finished</span>
            <input
              type="time"
              className="calInput"
              value={form.worked_end ?? ""}
              onChange={(e) => update("worked_end", e.target.value || null)}
            />
          </label>
        </div>

        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Tips</span>
            <input
              type="number"
              min={0}
              step="any"
              className="calInput"
              value={form.tip_amount || ""}
              onChange={(e) => update("tip_amount", Number(e.target.value) || 0)}
              placeholder="0.00"
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Tips paid</span>
            {/* Cash tips are money already in hand; tips paid through payroll
                arrive inside the cheque's gross. Recording both the same way
                would count the payroll ones twice. */}
            <select
              className="calInput"
              value={form.tip_is_cash ? "cash" : "cheque"}
              onChange={(e) => update("tip_is_cash", e.target.value === "cash")}
            >
              <option value="cash">In cash</option>
              <option value="cheque">On my cheque</option>
            </select>
          </label>

          <label className="calField">
            <span className="calFieldLabel">Rate, if different</span>
            <input
              type="number"
              min={0}
              step="any"
              className="calInput"
              value={form.rate_override ?? ""}
              onChange={(e) => update("rate_override", e.target.value === "" ? null : Number(e.target.value))}
              placeholder="job's rate"
            />
          </label>
        </div>

        <label className="calField">
          <span className="calFieldLabel">Notes</span>
          <input
            className="calInput"
            value={form.notes ?? ""}
            onChange={(e) => update("notes", e.target.value || null)}
            placeholder="Covered a late shift"
          />
        </label>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Saving…" : "Confirm shift"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
