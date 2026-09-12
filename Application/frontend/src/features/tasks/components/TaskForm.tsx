import { useState } from "react";
import { TaskCreate } from "../types";
import { Course } from "../../grades/types";

interface TaskFormProps {
  readonly courses: Course[];
  readonly onSubmit: (task: TaskCreate) => Promise<void>;
  readonly busy: boolean;
}

/**
 * What a due date means when no time is given: the end of that day.
 *
 * A deadline with no time is really "by the end of Friday", and leaving it null
 * made every task an all-day item on the calendar however specific the student
 * actually was. Pre-filled rather than forced, so anything due at 14:00 is one
 * edit away.
 */
const END_OF_DAY = "23:59";

function blankTask(): TaskCreate {
  return {
    title: "",
    notes: null,
    due_date: null,
    due_time: null,
    estimated_minutes: null,
    course_id: null,
    tags: [],
  };
}

/**
 * Adding a task.
 *
 * A real `<form>`, so `required` actually runs and Enter submits -- four forms
 * in this app were `<div>`s with a type="button" submit, where neither did
 * (audit #15).
 */
export default function TaskForm({ courses, onSubmit, busy }: TaskFormProps) {
  const [form, setForm] = useState<TaskCreate>(blankTask());
  const [tagText, setTagText] = useState("");

  function update<K extends keyof TaskCreate>(key: K, value: TaskCreate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  /** The two move together: a time of day with no date is rejected on save. */
  function setDueDate(value: string | null) {
    setForm((current) => ({
      ...current,
      due_date: value,
      due_time: value === null ? null : current.due_time ?? END_OF_DAY,
    }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    await onSubmit({
      ...form,
      title: form.title.trim(),
      tags: tagText.split(",").map((tag) => tag.trim()).filter(Boolean),
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

      <input
        type="number"
        min={1}
        max={2400}
        className="taskInput taskInputNarrow"
        // Number("") is 0, which would record "takes no time" rather than
        // "no estimate given".
        value={form.estimated_minutes ?? ""}
        onChange={(event) =>
          update("estimated_minutes", event.target.value === "" ? null : Number(event.target.value))
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
