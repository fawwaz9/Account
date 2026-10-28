import { useEffect, useState } from "react";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import { deleteImport, fetchImports } from "../api";
import { ImportSummary } from "../types";

/** Props for the account's import list. */
interface AccountImportsProps {
  readonly userId: string;
  readonly accountId: string;
  /** Bumped when the page reloads, so a fresh import shows up. */
  readonly nonce: number;
  /** Called after an undo, so the page reloads its balance and ledger. */
  readonly onUndone: () => void;
}

/**
 * This account's CSV imports, each undoable as one unit after a confirm.
 * Undo deletes every row the import wrote, edited ones included; renders nothing with no imports.
 */
export default function AccountImports({ userId, accountId, nonce, onUndone }: AccountImportsProps) {
  const [imports, setImports] = useState<ImportSummary[]>([]);
  const [undoing, setUndoing] = useState<ImportSummary | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchImports(userId)
      .then((all) => {
        if (!cancelled) setImports(all.filter((entry) => entry.account_id === accountId));
      })
      .catch(() => {
        if (!cancelled) setImports([]);
      });
    return () => { cancelled = true; };
  }, [userId, accountId, nonce, refresh]);

  async function confirmUndo() {
    if (!undoing) return;
    setSubmitting(true);
    setError(null);
    try {
      await deleteImport(userId, undoing.id);
      setUndoing(null);
      setRefresh((n) => n + 1);
      onUndone();
    } catch {
      setError("Couldn't undo that import. Nothing was removed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (imports.length === 0) return null;

  return (
    <section className="accountImports" aria-label="Imports">
      <h2>Imports</h2>
      <ul>
        {imports.map((entry) => (
          <li key={entry.id}>
            <span className="small-text">
              {entry.filename ?? "CSV import"} · {new Date(entry.created_at).toLocaleDateString()}
              {entry.first_date && entry.last_date ? ` · ${entry.first_date} to ${entry.last_date}` : ""}
            </span>
            <span className="small-text muted">
              {entry.rows_remaining} of {entry.row_count} rows still here
            </span>
            <button
              type="button"
              className="calButton"
              onClick={() => { setError(null); setUndoing(entry); }}
              disabled={entry.rows_remaining === 0 && entry.row_count === 0}
            >
              Undo
            </button>
          </li>
        ))}
      </ul>

      <DeleteConfirmModal
        open={undoing !== null}
        title="Undo this import?"
        message={
          undoing
            ? `This removes the ${undoing.rows_remaining} ${undoing.rows_remaining === 1 ? "row" : "rows"} it added to this account, including any you have edited since. This cannot be undone.`
            : ""
        }
        onConfirm={confirmUndo}
        onCancel={() => setUndoing(null)}
        submitting={submitting}
        error={error}
        confirmLabel="Undo import"
      />
    </section>
  );
}
