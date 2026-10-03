import { describe, expect, it } from "vitest";
import { ASSIGNMENT_HORIZON, DONE_LINGER_MS, groupByHorizon, withoutId } from "./horizon";
import { Task } from "./types";
import { addDays, today } from "../../shared/utils/dateUtils";

/**
 * Where a task sits, and what a just-ticked one does.
 *
 * The linger is the reason this file exists. A completed task used to leave its
 * group in the same frame the save landed, so the tick never appeared on screen —
 * the row simply vanished. These tests pin the behaviour that fixes it, including
 * the case that is easy to get backwards: a lingering row is shown *done* while
 * still filed where it was.
 */

function task(over: Partial<Task> = {}): Task {
  return {
    id: "t1",
    title: "Write up the lab",
    notes: null,
    due_date: addDays(today(), 3),
    due_time: null,
    estimated_minutes: null,
    tags: [],
    priority: 0,
    course_id: null,
    grade_id: null,
    recurring_id: null,
    occurrence_date: null,
    snoozed_until: null,
    done: false,
    completed_at: null,
    archived: false,
    created_at: null,
    ...over,
  } as Task;
}

const none: ReadonlySet<string> = new Set();

describe("groupByHorizon, without a linger", () => {
  it("files work due inside the fortnight as soon", () => {
    const groups = groupByHorizon([task({ due_date: addDays(today(), 3) })], none);

    expect(groups.soon).toHaveLength(1);
    expect(groups.later).toHaveLength(0);
  });

  it("files work past its date as overdue", () => {
    const groups = groupByHorizon([task({ due_date: addDays(today(), -1) })], none);

    expect(groups.overdue).toHaveLength(1);
  });

  it("files work beyond the fortnight as later", () => {
    const groups = groupByHorizon(
      [task({ due_date: addDays(today(), ASSIGNMENT_HORIZON + 1) })],
      none,
    );

    expect(groups.later).toHaveLength(1);
  });

  it("includes the last day of the fortnight in soon, not later", () => {
    // An off-by-one here drops a task due on day 14 out of the list it belongs in.
    const groups = groupByHorizon(
      [task({ due_date: addDays(today(), ASSIGNMENT_HORIZON) })],
      none,
    );

    expect(groups.soon).toHaveLength(1);
    expect(groups.later).toHaveLength(0);
  });

  it("files a dateless task as undated rather than guessing", () => {
    expect(groupByHorizon([task({ due_date: null })], none).undated).toHaveLength(1);
  });

  it("moves a completed task out of every dated group", () => {
    const groups = groupByHorizon([task({ done: true })], none);

    expect(groups.done).toHaveLength(1);
    expect(groups.soon).toHaveLength(0);
    expect(groups.overdue).toHaveLength(0);
  });
});

describe("the linger after a tick", () => {
  it("keeps a just-ticked task in the group it was already in", () => {
    // The whole point: it must NOT jump to done, or the row disappears from the
    // fortnight before the tick has been on screen for any length of time.
    const groups = groupByHorizon([task({ id: "t1" })], new Set(["t1"]));

    expect(groups.soon).toHaveLength(1);
    expect(groups.done).toHaveLength(0);
  });

  it("shows it as done while it lingers, so the tick and strike-through render", () => {
    // `.taskRowDone` carries both, and it is driven off this flag.
    const groups = groupByHorizon([task({ id: "t1", done: false })], new Set(["t1"]));

    expect(groups.soon[0].done).toBe(true);
  });

  it("does not mutate the task it was handed", () => {
    // It is handed rows from a hook's state; flipping `done` in place would make
    // the linger permanent and survive the set being cleared.
    const original = task({ id: "t1", done: false });

    groupByHorizon([original, task({ id: "t2" })], new Set(["t1"]));

    expect(original.done).toBe(false);
  });

  it("keeps a lingering overdue task in overdue, not in soon", () => {
    const groups = groupByHorizon(
      [task({ id: "t1", due_date: addDays(today(), -2) })],
      new Set(["t1"]),
    );

    expect(groups.overdue).toHaveLength(1);
    expect(groups.soon).toHaveLength(0);
  });

  it("keeps a lingering dateless task in undated", () => {
    const groups = groupByHorizon(
      [task({ id: "t1", due_date: null })],
      new Set(["t1"]),
    );

    expect(groups.undated).toHaveLength(1);
    expect(groups.undated[0].done).toBe(true);
  });

  it("lets it move to done once the linger is cleared", () => {
    // What the timeout does: same task, now actually done and no longer held.
    const groups = groupByHorizon([task({ id: "t1", done: true })], none);

    expect(groups.done).toHaveLength(1);
    expect(groups.soon).toHaveLength(0);
  });

  it("holds only the task that was ticked", () => {
    const groups = groupByHorizon(
      [task({ id: "t1" }), task({ id: "t2" }), task({ id: "t3", done: true })],
      new Set(["t1"]),
    );

    expect(groups.soon.map((t) => t.id)).toEqual(["t1", "t2"]);
    expect(groups.done.map((t) => t.id)).toEqual(["t3"]);
  });

  it("pauses long enough to be seen and short enough not to be waited for", () => {
    // Asked for as three tenths of a second.
    expect(DONE_LINGER_MS).toBe(300);
  });
});

describe("withoutId", () => {
  it("removes the id", () => {
    expect([...withoutId(new Set(["a", "b"]), "a")]).toEqual(["b"]);
  });

  it("returns the same set when there is nothing to remove", () => {
    // Identity matters: a new Set every toggle would re-run the grouping memo and
    // re-render every group for an unrelated click.
    const ids = new Set(["a"]);

    expect(withoutId(ids, "zzz")).toBe(ids);
  });

  it("does not mutate the set it was given", () => {
    const ids = new Set(["a", "b"]);

    withoutId(ids, "a");

    expect(ids.has("a")).toBe(true);
  });
});
