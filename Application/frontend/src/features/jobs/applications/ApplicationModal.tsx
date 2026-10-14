import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import { addStep, createApplication, deleteApplication, deleteStep, updateApplication } from "./api";
import {
  Application, ApplicationInput, ApplicationStatus, OfferPeriod, STATUS_LABELS, STEP_STATUSES, Step,
} from "./types";
import { useAuth } from "../../../app/auth/AuthContext";
import { shortDate, today } from "../../../shared/utils/dateUtils";

interface Props {
  readonly open: boolean;
  readonly application: Application | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

function formFor(application: Application | null): ApplicationInput {
  return {
    company: application?.company ?? "",
    role: application?.role ?? "",
    applied_on: application?.applied_on ?? today(),
    source: application?.source ?? null,
    link: application?.link ?? null,
    location: application?.location ?? null,
    notes: application?.notes ?? null,
    deadline: application?.deadline ?? null,
    follow_up_on: application?.follow_up_on ?? null,
    offer_amount: application?.offer_amount ?? null,
    offer_period: application?.offer_period ?? null,
  };
}

/**
 * One application: its details, its history, and what happened next (D2).
 *
 * The history is a list of dated steps, never an overwritten status, so a
 * step entered by mistake is taken back rather than edited -- the first,
 * "applied", goes only with the application.
 */
export default function ApplicationModal({ open, application, onClose, onSaved }: Props) {
  const { user } = useAuth();
  const [form, setForm] = useState<ApplicationInput>(formFor(application));
  const [next, setNext] = useState<{ status: ApplicationStatus; on_date: string; note: string }>(
    { status: "screening", on_date: today(), note: "" });
  const [current, setCurrent] = useState<Application | null>(application);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const [removingStep, setRemovingStep] = useState<Step | null>(null);

  useEffect(() => {
    setForm(formFor(application));
    setCurrent(application);
    setNext({ status: "screening", on_date: today(), note: "" });
    setError(null);
  }, [application, open]);

  if (!open) return null;

  function update<K extends keyof ApplicationInput>(key: K, value: ApplicationInput[K]) {
    setForm((was) => ({ ...was, [key]: value }));
  }

  async function run(action: () => Promise<Application | unknown>, close = false) {
    if (!user) return;
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      if (result && typeof result === "object" && "steps" in result) setCurrent(result as Application);
      onSaved();
      if (close) onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that");
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;
    void run(() => (current
      ? updateApplication(user.id, current.id, form)
      : createApplication(user.id, form)), true);
  }

  const showsOffer = form.offer_amount !== null
    || (current && ["offer", "accepted"].includes(current.status));

  return (
    <>
      <Modal title={current ? `${current.company}: ${current.role}` : "New application"} onClose={onClose}
        panelClassName="widePopup">
        <form className="calForm" onSubmit={handleSubmit}>
          <div className="calRow">
            <label className="calField">
              <span className="calFieldLabel">Company</span>
              <input className="calInput" value={form.company} required
                onChange={(e) => update("company", e.target.value)} placeholder="Shopify" />
            </label>
            <label className="calField">
              <span className="calFieldLabel">Role</span>
              <input className="calInput" value={form.role} required
                onChange={(e) => update("role", e.target.value)} placeholder="Backend developer intern" />
            </label>
          </div>
          <div className="calRow">
            <label className="calField">
              <span className="calFieldLabel">Applied on</span>
              <input type="date" className="calInput" value={form.applied_on} required
                onChange={(e) => update("applied_on", e.target.value)} />
            </label>
            <label className="calField">
              <span className="calFieldLabel">Found it through</span>
              <input className="calInput" value={form.source ?? ""}
                onChange={(e) => update("source", e.target.value || null)} placeholder="SCOPE, a referral, a career fair" />
            </label>
          </div>
          <div className="calRow">
            <label className="calField">
              <span className="calFieldLabel">Deadline</span>
              <input type="date" className="calInput" value={form.deadline ?? ""}
                onChange={(e) => update("deadline", e.target.value || null)} />
            </label>
            <label className="calField">
              <span className="calFieldLabel">Follow up on</span>
              <input type="date" className="calInput" value={form.follow_up_on ?? ""}
                onChange={(e) => update("follow_up_on", e.target.value || null)} />
            </label>
          </div>
          <p className="small-text muted">Deadlines and follow-ups show on your calendar too.</p>
          <div className="calRow">
            <label className="calField">
              <span className="calFieldLabel">Location</span>
              <input className="calInput" value={form.location ?? ""}
                onChange={(e) => update("location", e.target.value || null)} placeholder="Vancouver, remote" />
            </label>
            <label className="calField">
              <span className="calFieldLabel">Link</span>
              <input className="calInput" value={form.link ?? ""}
                onChange={(e) => update("link", e.target.value || null)} placeholder="The posting" />
            </label>
          </div>
          <div className="calRow">
            <label className="calField">
              <span className="calFieldLabel">Notes</span>
              <textarea className="calInput" rows={2} value={form.notes ?? ""}
                onChange={(e) => update("notes", e.target.value || null)} />
            </label>
          </div>

          {showsOffer && (
            <div className="calRow">
              <label className="calField">
                <span className="calFieldLabel">Pay offered (only you see this)</span>
                <input type="number" min={0} step="any" className="calInput" value={form.offer_amount ?? ""}
                  onChange={(e) => {
                    const amount = e.target.value === "" ? null : Number(e.target.value);
                    setForm((was) => ({
                      ...was, offer_amount: amount,
                      offer_period: amount === null ? null : was.offer_period ?? "hourly",
                    }));
                  }} />
              </label>
              <label className="calField">
                <span className="calFieldLabel">Per</span>
                <select className="calInput" value={form.offer_period ?? "hourly"} disabled={form.offer_amount === null}
                  onChange={(e) => update("offer_period", e.target.value as OfferPeriod)}>
                  <option value="hourly">Hour</option>
                  <option value="monthly">Month</option>
                  <option value="yearly">Year</option>
                </select>
              </label>
            </div>
          )}

          {error && <p className="calError">{error}</p>}

          <div className="calFormActions">
            {current && (
              <button type="button" className="calButton" onClick={() => setRemoving(true)} disabled={busy}>
                Delete
              </button>
            )}
            <button type="button" className="calButton" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="calButton calButtonPrimary" disabled={busy}>
              {busy ? "Saving…" : current ? "Save" : "Add application"}
            </button>
          </div>
        </form>

        {current && (
          <section className="appHistory" aria-label="History">
            <h3 className="appHistoryTitle">History</h3>
            <ol className="appSteps">
              {current.steps.map((step) => (
                <li key={step.id} className="appStep">
                  <span className={`appStatus appStatus-${step.status}`}>{STATUS_LABELS[step.status]}</span>
                  <span className="small-text muted">{shortDate(step.on_date)}</span>
                  {step.note && <span className="small-text">{step.note}</span>}
                  {step.status !== "applied" && (
                    <button type="button" className="calButton appStepRemove" disabled={busy}
                      onClick={() => setRemovingStep(step)}
                      aria-label={`Remove the ${STATUS_LABELS[step.status]} step on ${step.on_date}`}>
                      Remove
                    </button>
                  )}
                </li>
              ))}
            </ol>

            <form className="calRow appNext" onSubmit={(event) => {
              event.preventDefault();
              if (!user) return;
              void run(() => addStep(user.id, current.id,
                { status: next.status, on_date: next.on_date, note: next.note.trim() || null }));
              setNext((was) => ({ ...was, note: "" }));
            }}>
              <label className="calField">
                <span className="calFieldLabel">What happened</span>
                <select className="calInput" value={next.status}
                  onChange={(e) => setNext((was) => ({ ...was, status: e.target.value as ApplicationStatus }))}>
                  {STEP_STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}
                </select>
              </label>
              <label className="calField">
                <span className="calFieldLabel">On</span>
                <input type="date" className="calInput" value={next.on_date} required
                  onChange={(e) => setNext((was) => ({ ...was, on_date: e.target.value }))} />
              </label>
              <label className="calField">
                <span className="calFieldLabel">Note</span>
                <input className="calInput" value={next.note} placeholder="Second round, with the team lead"
                  onChange={(e) => setNext((was) => ({ ...was, note: e.target.value }))} />
              </label>
              <button type="submit" className="calButton calButtonPrimary" disabled={busy}>Add update</button>
            </form>
          </section>
        )}
      </Modal>

      <DeleteConfirmModal
        open={removing}
        title="Delete this application?"
        message={current ? `"${current.company}: ${current.role}" and its whole history will be deleted.` : ""}
        confirmLabel="Delete the application"
        submitting={busy}
        error={error}
        onCancel={() => setRemoving(false)}
        onConfirm={() => {
          setRemoving(false);
          if (user && current) void run(() => deleteApplication(user.id, current.id), true);
        }}
      />
      <DeleteConfirmModal
        open={removingStep !== null}
        title="Remove this step?"
        message={removingStep ? `The ${STATUS_LABELS[removingStep.status]} step on ${removingStep.on_date} will be removed from the history.` : ""}
        confirmLabel="Remove the step"
        submitting={busy}
        error={error}
        onCancel={() => setRemovingStep(null)}
        onConfirm={() => {
          const target = removingStep;
          setRemovingStep(null);
          if (user && current && target) void run(() => deleteStep(user.id, current.id, target.id));
        }}
      />
    </>
  );
}
