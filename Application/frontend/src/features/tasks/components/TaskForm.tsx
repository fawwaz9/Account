import { useState } from "react";
import { DEFAULT_PRIORITY, MAX_PRIORITY, MIN_PRIORITY, PRIORITY_LABELS, TaskCreate } from "../types";
import { numberOrNull, parseTags, withDueDate } from "../taskFields";

/** Every priority step, lowest first, for the select. */
const PRIORITY_STEPS = Array.from(
  { length: MAX_PRIORITY - MIN_PRIORITY + 1 },
  (_, index) => MIN_PRIORITY + index
);
import { Course } from "../../grades/types";

/** The courses to pick from, the save handler, and a busy flag. */
interface TaskFormProps {
  readonly courses: Course[];
  readonly onSubmit: (task: TaskCreate) => Promise<void>;
  readonly busy: boolean;
}

/** An empty task at the default priority. */
function blankTask(): TaskCreate {
  return {
    title: "",
    notes: null,
    due_date: null,
    due_time: null,
    estimated_minutes: null,
    course_id: null,
    tags: [],
    // Coursework gets its priority from the grade's category; a task typed in
    // here has no category to read, so it starts in the middle of the scale.
    priority: DEFAULT_PRIORITY,
  };
}

/** The add-task row on the Tasks page: title, course, date and time, priority, estimate, tags. */
export default function TaskForm({ courses, onSubmit, busy }: TaskFormProps) {
  const [form, setForm] = useState<TaskCreate>(blankTask());
  const [tagText, setTagText] = useState("");

  function update<K extends keyof TaskCreate>(key: K, value: TaskCreate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  /** The two move together: a time of day with no date is rejected on save. */
  function setDueDate(value: string | null) {
    setForm((current) => withDueDate(current, value));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    await onSubmit({
      ...form,
      title: form.title.trim(),
      tags: parseTags(tagText),
    });

    setForm(blankTask());
    setTagText("");
  }

  return (
    <form className="taskForm" onSubmit={handleSubmit}>
      <input
        className="taskInput taskInputWide"
        value={form.title}
        onChange={(event) => update("title", event.target.value)}
        placeholder="What needs doing?"
        aria-label="Task title"
        required
      />

      <select
        className="taskInput"
        value={form.course_id ?? ""}
        onChange={(event) => update("course_id", event.target.value || null)}
        aria-label="Course"
      >
        <option value="">No course</option>
        {courses.map((course) => (
          <option key={course.id} value={course.id}>{course.code}</option>
        ))}
      </select>

      <input
        type="date"
        className="taskInput"
        value={form.due_date ?? ""}
        onChange={(event) => setDueDate(event.target.value || null)}
        aria-label="Due date"
      />

      {/* Only once there is a date to attach it to. A time on its own is not a
          deadline, and the API refuses one. */}
      {form.due_date && (
        <input
          type="time"
          className="taskInput taskInputNarrow"
          value={form.due_time ?? ""}
          onChange={(event) => update("due_time", event.target.value || null)}
          aria-label="Due time"
        />
      )}

      <select
        className="taskInput taskInputNarrow"
        value={form.priority}
        onChange={(event) => update("priority", Number(event.target.value))}
        aria-label="Priority"
      >
        {PRIORITY_STEPS.map((step) => (
          <option key={step} value={step}>{step} · {PRIORITY_LABELS[step]}</option>
        ))}
      </select>

      <input
        type="number"
        min={1}
        max={2400}
        className="taskInput taskInputNarrow"
        value={form.estimated_minutes ?? ""}
        onChange={(event) =>
          update("estimated_minutes", numberOrNull(event.target.value))
        }
        placeholder="mins"
        aria-label="Estimated minutes"
      />

      <input
        className="taskInput"
        value={tagText}
        onChange={(event) => setTagText(event.target.value)}
        placeholder="tags, comma separated"
        aria-label="Tags, comma separated"
      />

      <button type="submit" className="calButton calButtonPrimary" disabled={busy}>
        {busy ? "Adding..." : "Add"}
      </button>
    </form>
  );
}
