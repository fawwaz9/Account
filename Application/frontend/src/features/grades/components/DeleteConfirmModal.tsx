import Modal from "../../../shared/components/Modal";

/** The dialog's title and message, its confirm and cancel handlers, and its status. */
interface DeleteConfirmModalProps {
  readonly open: boolean;
  readonly title: string;
  readonly message: string;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
  readonly submitting: boolean;
  readonly error?: string | null;
  /** Label for the primary button. Defaults to "Delete". */
  readonly confirmLabel?: string;
  /** A narrower destructive choice, such as one row of a group; omitted, only the primary shows. */
  readonly secondaryAction?: { readonly label: string; readonly onConfirm: () => void };
}

/** The confirmation each permanent delete goes through, with an optional narrower second choice. */
export default function DeleteConfirmModal({
  open,
  title,
  message,
  onConfirm,
  onCancel,
  submitting,
  error,
  confirmLabel = "Delete",
  secondaryAction,
}: DeleteConfirmModalProps) {
  if (!open) return null;

  return (
    <Modal title={title} onClose={onCancel}>
      <p className="text-sm text-slate-200">{message}</p>

      {error && (
        <div className="space-y-1">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      <div className="flex justify-end gap-3 pt-4">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200"
          disabled={submitting}
        >
          Cancel
        </button>
        {secondaryAction && (
          <button
            type="button"
            onClick={secondaryAction.onConfirm}
            className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200"
            disabled={submitting}
          >
            {secondaryAction.label}
          </button>
        )}

        <button
          type="button"
          onClick={onConfirm}
          className="rounded-lg !bg-red-600 !text-white"
          disabled={submitting}
        >
          {submitting ? "Deleting..." : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}