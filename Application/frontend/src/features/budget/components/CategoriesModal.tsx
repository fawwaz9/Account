import { useEffect, useState } from "react";
import { createCategory, deleteCategory, updateCategory } from "../api";
import { SpendCategory } from "../types";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";
import Modal from "../../../shared/components/Modal";

/** Props for the categories dialog. */
interface CategoriesModalProps {
  readonly open: boolean;
  readonly categories: readonly SpendCategory[];
  readonly onClose: () => void;
  /** Called after each change, so the page reloads its categories. */
  readonly onSaved: () => void;
}

/**
 * Add, rename, archive and delete spending categories; a rename saves on blur.
 * Delete asks in the row first and removes only the label: its expenses become uncategorised.
 */
export default function CategoriesModal({
  open,
  categories,
  onClose,
  onSaved,
}: CategoriesModalProps) {
  const { user } = useAuth();
  const [names, setNames] = useState<Record<string, string>>({});
  const [adding, setAdding] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setAdding("");
    setConfirmingDelete(null);
    setNames(Object.fromEntries(categories.map((c) => [c.id, c.name])));
  }, [open, categories]);

  if (!open) return null;

  async function run(id: string, work: () => Promise<unknown>) {
    if (!user) return;
    setBusyId(id);
    setError(null);
    try {
      await work();
      onSaved();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Modal title="Spending categories" onClose={onClose}>
      <div className="loginForm">
        <ul className="categoryEditList">
          {categories.map((category) => (
            <li className="categoryEditRow" key={category.id}>
              <input
                className="loginInput"
                aria-label={`Rename ${category.name}`}
                value={names[category.id] ?? ""}
                disabled={busyId === category.id}
                onChange={(event) =>
                  setNames((prev) => ({ ...prev, [category.id]: event.target.value }))
                }
                onBlur={() => {
                  const next = (names[category.id] ?? "").trim();
                  if (!next || next === category.name) return;
                  run(category.id, () => updateCategory(user!.id, category.id, { name: next }));
                }}
              />

              <button
                type="button"
                className="categoryEditAction"
                disabled={busyId === category.id}
                onClick={() =>
                  run(category.id, () =>
                    updateCategory(user!.id, category.id, { archived: !category.archived })
                  )
                }
                title={
                  category.archived
                    ? "Bring it back into the picker"
                    : "Keep its history but stop offering it"
                }
              >
                {category.archived ? "Unarchive" : "Archive"}
              </button>

              {confirmingDelete === category.id ? (
                <>
                  <button
                    type="button"
                    className="categoryEditAction categoryEditDanger"
                    disabled={busyId === category.id}
                    onClick={() =>
                      run(category.id, async () => {
                        await deleteCategory(user!.id, category.id);
                        setConfirmingDelete(null);
                      })
                    }
                  >
                    Yes, delete
                  </button>
                  <button
                    type="button"
                    className="categoryEditAction"
                    onClick={() => setConfirmingDelete(null)}
                  >
                    Keep
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="categoryEditAction categoryEditDanger"
                  disabled={busyId === category.id}
                  onClick={() => setConfirmingDelete(category.id)}
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>

        {confirmingDelete && (
          <p className="small-text muted" role="alert">
            Deleting a category removes the label only. The expenses it was on
            are kept, and become uncategorised.
          </p>
        )}

        <div className="categoryAddRow">
          <input
            className="loginInput"
            placeholder="New category"
            aria-label="New category name"
            value={adding}
            onChange={(event) => setAdding(event.target.value)}
          />
          <button
            type="button"
            className="buttons addCourseButton"
            disabled={!adding.trim() || busyId === "new"}
            onClick={() =>
              run("new", async () => {
                await createCategory(user!.id, adding.trim());
                setAdding("");
              })
            }
          >
            Add
          </button>
        </div>

        {error && <p className="loginError">{error}</p>}

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" className="loginSubmit" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </Modal>
  );
}
