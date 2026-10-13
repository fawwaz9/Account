import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import HelpTip from "../../../shared/components/HelpTip";
import RecurrenceEditor from "../../calender/components/RecurrenceEditor";
import PayDaysEditor, { startingPayDays } from "./PayDaysEditor";
import { createJob, deleteJob, updateJob } from "../api";
import { Job, JOB_KIND_LABELS, JobCreate, JobKind } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { today } from "../../../shared/utils/dateUtils";

interface JobModalProps {
  readonly open: boolean;
  readonly job: Job | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

function blankJob(): JobCreate {
  return {
    name: "",
    employer: null,
    kind: JobKind.HOURLY,
    hourly_rate: null,
    period_amount: null,
    started_on: today(),
    ended_on: null,
    pay_starts_on: null,
    pay_schedule: null,
    pay_days: null,
    archived: false,
  };
}

function formFor(job: Job | null): JobCreate {
  if (!job) return blankJob();
  return {
    name: job.name,
    employer: job.employer,
    kind: job.kind,
    hourly_rate: job.hourly_rate,
    period_amount: job.period_amount,
    started_on: job.started_on,
    ended_on: job.ended_on,
    pay_starts_on: job.pay_starts_on,
    pay_schedule: job.pay_schedule,
    pay_days: job.pay_days ?? null,
    archived: job.archived,
  };
}

export default function JobModal({ open, job, onClose, onSaved }: JobModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<JobCreate>(formFor(job));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Removing a job takes its shifts and its paycheques with it, so it asks. The
  // confirmation stacks over this editor, which is the case `Modal`'s own Escape
  // stack exists for -- only the top dialog answers the keystroke.
  const [confirmingRemoval, setConfirmingRemoval] = useState(false);

  useEffect(() => {
    setForm(formFor(job));
    setError(null);
  }, [job, open]);

  if (!open) return null;

  function update<K extends keyof JobCreate>(key: K, value: JobCreate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  /**
   * Changing the kind clears the other kind's pay field.
   *
   * The API refuses a job holding both, and rightly: two answers to "what
   * should this have paid" with nothing to choose between them.
   */
  function setKind(kind: JobKind) {
    setForm((current) => ({
      ...current,
      kind,
      hourly_rate: kind === JobKind.HOURLY ? current.hourly_rate : null,
      period_amount: kind === JobKind.SALARIED ? current.period_amount : null,
    }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSaving(true);
    setError(null);
    try {
      const payload = { ...form, name: form.name.trim() };
      if (job) await updateJob(user.id, job.id, payload);
      else await createJob(user.id, payload);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this job");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!user || !job) return;
    setSaving(true);
    setError(null);
    try {
      await deleteJob(user.id, job.id);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove this job");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
    <Modal title={job ? "Edit job" : "New job"} onClose={onClose} panelClassName="widePopup">
      <form className="calForm" onSubmit={handleSubmit}>
        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Job</span>
            <input
              className="calInput"
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="Campus Bookstore"
              required
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Employer</span>
            <input
              className="calInput"
              value={form.employer ?? ""}
              onChange={(e) => update("employer", e.target.value || null)}
              placeholder="UBC"
            />
          </label>
        </div>

        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">How it pays</span>
            <select
              className="calInput"
              value={form.kind}
              onChange={(e) => setKind(e.target.value as JobKind)}
            >
              {Object.values(JobKind).map((kind) => (
                <option key={kind} value={kind}>{JOB_KIND_LABELS[kind]}</option>
              ))}
            </select>
          </label>

          {/* Only the field this kind of job actually has. */}
          {form.kind === JobKind.HOURLY && (
            <label className="calField">
              <span className="calFieldLabel">Hourly rate</span>
              <input
                type="number"
                min={0}
                step="any"
                className="calInput"
                value={form.hourly_rate ?? ""}
                onChange={(e) => update("hourly_rate", e.target.value === "" ? null : Number(e.target.value))}
                placeholder="18.50"
                required
              />
            </label>
          )}

          {form.kind === JobKind.SALARIED && (
            <label className="calField">
              <span className="calFieldLabel">Per pay period</span>
              <input
                type="number"
                min={0}
                step="any"
                className="calInput"
                value={form.period_amount ?? ""}
                onChange={(e) => update("period_amount", e.target.value === "" ? null : Number(e.target.value))}
                placeholder="1200.00"
                required
              />
            </label>
          )}

          {form.kind === JobKind.CONTRACT && (
            <p className="small-text muted calField">
              Contract work is billed per invoice, so there is no rate to set here.
            </p>
          )}
        </div>

        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Started</span>
            <input
              type="date"
              className="calInput"
              value={form.started_on ?? ""}
              onChange={(e) => update("started_on", e.target.value || null)}
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Ended</span>
            <input
              type="date"
              className="calInput"
              value={form.ended_on ?? ""}
              onChange={(e) => update("ended_on", e.target.value || null)}
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">First pay date</span>
            <input
              type="date"
              className="calInput"
              value={form.pay_starts_on ?? ""}
              onChange={(e) => update("pay_starts_on", e.target.value || null)}
            />
          </label>
        </div>

        {/* Named, because a bare repeat editor on a job form reads as though it
            governs the shifts. It does not: shifts are added on their own, and
            this is only how often the money arrives. Safe-to-spend reads it to
            decide how long your balance has to last. */}
        <fieldset className="payRepeat">
          <legend className="calFieldLabel">Does the paycheque repeat?</legend>
          <HelpTip label="What the pay schedule means">
            How often you are paid, not when you work — shifts are added separately.
            Leave the date empty if the pay is irregular and nothing will be predicted.
          </HelpTip>

          {form.pay_starts_on ? (
            <>
              {/* A repeat, or set days of the month: the second says what the
                  first cannot ("the 15th and the last day", "the last Friday"),
                  and a job pays by one or the other, never both. */}
              <div className="calRow" role="radiogroup" aria-label="Pay schedule kind">
                <label className="payDaysChoice">
                  <input
                    type="radio"
                    checked={form.pay_days === null}
                    onChange={() => setForm((current) => ({ ...current, pay_days: null }))}
                  />
                  A repeat
                </label>
                <label className="payDaysChoice">
                  <input
                    type="radio"
                    checked={form.pay_days !== null}
                    onChange={() => setForm((current) => ({
                      ...current,
                      pay_schedule: null,
                      pay_days: startingPayDays(current.pay_starts_on as string),
                    }))}
                  />
                  Set days of the month
                </label>
              </div>

              {form.pay_days ? (
                <PayDaysEditor value={form.pay_days} onChange={(days) => update("pay_days", days)} />
              ) : (
                <RecurrenceEditor
                  value={form.pay_schedule}
                  onChange={(schedule) => update("pay_schedule", schedule)}
                  startsOn={form.pay_starts_on}
                />
              )}
            </>
          ) : (
            <p className="small-text muted">
              Set a first pay date above to say how often it repeats.
            </p>
          )}
        </fieldset>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          {job && (
            <button
              type="button"
              className="calButton"
              onClick={() => setConfirmingRemoval(true)}
              disabled={saving}
            >
              Remove
            </button>
          )}
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Saving…" : job ? "Save job" : "Add job"}
          </button>
        </div>
      </form>
    </Modal>

    <DeleteConfirmModal
      open={confirmingRemoval}
      title="Remove this job?"
      message={
        job
          ? `"${job.name}" will be removed, and so will every shift and paycheque ` +
            `recorded against it. Transactions already in the ledger stay where ` +
            `they are; what goes is the job and its record of hours and pay.`
          : ""
      }
      confirmLabel="Remove the job"
      submitting={saving}
      error={error}
      onCancel={() => setConfirmingRemoval(false)}
      onConfirm={async () => {
        setConfirmingRemoval(false);
        await handleDelete();
      }}
    />
    </>
  );
}
