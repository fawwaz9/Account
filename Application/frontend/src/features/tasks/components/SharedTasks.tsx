import { FormEvent, useEffect, useState } from "react";
import HelpTip from "../../../shared/components/HelpTip";
import { dueLabel } from "../../../shared/utils/dateUtils";
import { SharedTask, fetchSharedTasks, leaveSharedTask, updateSharedTask } from "../sharing";

/** The signed-in user's id. */
interface Props {
  readonly userId: string;
}

/**
 * Other people's tasks you are on: tick for everyone, edit the title and notes, or leave once
 * confirmed. Renders nothing when there are none or the read fails.
 */
export default function SharedTasks({ userId }: Props) {
  const [tasks, setTasks] = useState<SharedTask[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [leaving, setLeaving] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setTasks(await fetchSharedTasks(userId));
    } catch {
      setTasks(null);
    }
  }

  useEffect(() => { void load(); }, [userId]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!tasks || tasks.length === 0) return null;

  async function act(step: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await step();
      await load();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function startEdit(task: SharedTask) {
    setEditing(task.task_id);
    setTitle(task.title);
    setNotes(task.notes ?? "");
  }

  function save(event: FormEvent, task: SharedTask) {
    event.preventDefault();
    void act(async () => {
      await updateSharedTask(userId, task.task_id, { title: title.trim(), notes: notes.trim() ? notes : null });
      setEditing(null);
    });
  }

  return (
    <section className="taskGroup sharedTasks" aria-label="Shared with you">
      <header className="taskGroupHeader">
        <h2 className="taskGroupTitle">Shared with you</h2>
        <HelpTip label="About shared tasks">
          Tasks someone shared with you through a link. Ticking one closes it for everyone. You can edit
          its title and notes, and leave it. It doesn&rsquo;t count in your own week or your partner figure.
        </HelpTip>
      </header>
      <ul className="taskItems">
        {tasks.map((task) => (
          <li key={task.task_id} className={`taskRow${task.done ? " taskRowDone" : ""}`}>
            <button type="button" className="taskCheck" disabled={busy} aria-pressed={task.done}
                    aria-label={`${task.done ? "Reopen" : "Complete"} ${task.title}`}
                    onClick={() => void act(() => updateSharedTask(userId, task.task_id, { done: !task.done }))}>
              <span aria-hidden="true">{task.done ? "✓" : ""}</span>
            </button>
            <div className="taskBody">
              {editing === task.task_id ? (
                <form className="sharedTaskEdit" onSubmit={(event) => save(event, task)}>
                  <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required
                         aria-label="Title" />
                  <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000}
                            aria-label="Notes" rows={2} />
                  <span className="catalogueActions">
                    <button type="submit" className="calButton calButtonPrimary" disabled={busy || !title.trim()}>
                      Save
                    </button>
                    <button type="button" className="calButton" onClick={() => setEditing(null)}>Cancel</button>
                  </span>
                </form>
              ) : (
                <>
                  <p className="taskTitle">{task.title}</p>
                  <div className="taskMeta">
                    {task.due_date && <span className="taskDue">{dueLabel(task.due_date)}</span>}
                    <span className="taskTag taskTagShared">
                      {task.owner_name}&rsquo;s · with {task.member_names.join(", ")}
                    </span>
                  </div>
                  {task.notes && <p className="taskNotes">{task.notes}</p>}
                </>
              )}
              {leaving === task.task_id && (
                <span className="catalogueActions">
                  <span className="small-text">Leave it? You&rsquo;d need a new link from {task.owner_name} to rejoin.</span>
                  <button type="button" className="calButton calButtonDanger" disabled={busy}
                          onClick={() => void act(async () => {
                            await leaveSharedTask(userId, task.task_id);
                            setLeaving(null);
                          })}>
                    Leave
                  </button>
                  <button type="button" className="calButton" onClick={() => setLeaving(null)}>Stay</button>
                </span>
              )}
            </div>
            {editing !== task.task_id && (
              <button type="button" className="taskEdit" disabled={busy} onClick={() => startEdit(task)}
                      aria-label={`Edit ${task.title}`}>
                Edit
              </button>
            )}
            {leaving !== task.task_id && editing !== task.task_id && (
              <button type="button" className="taskSnooze" disabled={busy} onClick={() => setLeaving(task.task_id)}
                      aria-label={`Leave ${task.title}`}>
                Leave
              </button>
            )}
          </li>
        ))}
      </ul>
      {error && <p className="small-text error" role="alert">{error}</p>}
    </section>
  );
}
