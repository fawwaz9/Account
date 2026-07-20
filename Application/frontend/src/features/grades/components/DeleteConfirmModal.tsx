interface DeleteConfirmModalProps {
  readonly open: boolean;
  readonly title: string;
  readonly message: string;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
  readonly submitting: boolean;
  readonly error?: string | null;
}

export default function DeleteConfirmModal({
  open,
  title,
  message,
  onConfirm,
  onCancel,
  submitting,
  error,
}: DeleteConfirmModalProps) {
  if (!open) return null;

  return (
    <div className="popup">
      <div className="addCoursePopup">
        <h2>{title}</h2>
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
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg !bg-red-600 !text-white"
            disabled={submitting}
          >
            {submitting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}