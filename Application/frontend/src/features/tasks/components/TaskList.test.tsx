// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import TaskList from "./TaskList";
import { Task } from "../types";

/**
 * What a group says when it has nothing to show.
 *
 * The bug this pins: turning on "show completed" refetches, but the rows already
 * in state are the pre-toggle ones, so "Done" rendered with zero tasks and
 * asserted "Nothing finished yet." -- a true statement about the OLD answer,
 * read as the new one -- and then filled in a moment later. An empty message is
 * a claim about the data, and a group may not make it before the data arrives.
 */

function task(over: Partial<Task> = {}): Task {
  return {
    id: "t-1",
    title: "Problem set",
    notes: null,
    due_date: "2026-10-10",
    due_time: null,
    estimated_minutes: 60,
    course_id: null,
    course_code: null,
    tags: [],
    priority: 2,
    done: false,
    completed_at: null,
    archived: false,
    created_at: null,
    grade_id: null,
    recurring_id: null,
    risk: null,
    snoozed_until: null,
    snooze_count: 0,
    last_snooze_reason: null,
    ...over,
  };
}

const handlers = {
  onToggle: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  onPriority: vi.fn(),
  onSnooze: vi.fn(),
  onWake: vi.fn(),
  busy: false,
};

afterEach(cleanup);

describe("TaskList while its rows are still loading", () => {
  it("says it is loading instead of claiming the group is empty", () => {
    render(
      <TaskList title="Done" tasks={[]} emptyMessage="Nothing finished yet." loading {...handlers} />,
    );

    expect(screen.getByText("Loading…")).toBeTruthy();
    expect(screen.queryByText("Nothing finished yet.")).toBeNull();
  });

  it("shows the empty message once loading is over", () => {
    render(
      <TaskList title="Done" tasks={[]} emptyMessage="Nothing finished yet." {...handlers} />,
    );

    expect(screen.getByText("Nothing finished yet.")).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();
  });

  it("withholds the count too, rather than announcing nought tasks", () => {
    render(<TaskList title="Done" tasks={[]} loading {...handlers} />);

    expect(screen.queryByText(/0 tasks/)).toBeNull();
  });

  it("states the count as soon as it is known to be nought", () => {
    render(<TaskList title="Done" tasks={[]} {...handlers} />);

    expect(screen.getByText(/0 tasks/)).toBeTruthy();
  });

  it("announces the wait to a screen reader, since nothing visual moves", () => {
    render(<TaskList title="Done" tasks={[]} loading {...handlers} />);

    expect(screen.getByRole("status").textContent).toBe("Loading…");
  });

  it("does not announce an empty message as a status", () => {
    render(<TaskList title="Done" tasks={[]} emptyMessage="Nothing finished yet." {...handlers} />);

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("keeps rows it already has rather than replacing them with a spinner", () => {
    // A plain reload must not make the page restless: rows already on screen are
    // still the answer, so loading is only ever shown in place of an EMPTY group.
    render(<TaskList title="Overdue" tasks={[task()]} loading {...handlers} />);

    expect(screen.getByText("Problem set")).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();
    expect(screen.getByText(/1 task/)).toBeTruthy();
  });
});

/**
 * The prop is actually passed.
 *
 * A `loading` prop that defaults to false is useless if nothing supplies it, and
 * that exact failure shipped earlier today: ten confirmation dialogs were written
 * correctly and six were never wired to anything. The component tests above prove
 * the behaviour; this proves it is reachable from the page the bug was reported
 * against, which is the half a component test cannot see.
 */
describe("TasksPage wires its lists to the loading state", () => {
  const source = readFileSync(join(__dirname, "../../../pages/TasksPage.tsx"), "utf8");

  /** Each `<TaskList ... />` element in the page, as source text. */
  const lists = [...source.matchAll(/<TaskList\b[\s\S]*?\/>/g)].map((m) => m[0]);

  it("renders the lists this test assumes it does", () => {
    // Guards the regex itself: if the page stops matching, the assertions below
    // would vacuously pass over an empty array.
    expect(lists.length).toBe(4);
  });

  it("gives every list the loading state, the Done list included", () => {
    const unwired = lists
      .filter((list) => !/\bloading=\{stale\}/.test(list))
      .map((list) => list.match(/title=\{?["`]?([^"`}\n]+)/)?.[1] ?? list.slice(0, 60));

    expect(unwired).toEqual([]);
  });

  it("reads `stale` from the hook rather than plain `loading`", () => {
    // `loading` is also true during a plain reload, when the rows on screen are
    // still correct. Wiring the lists to it would flicker every empty group on
    // every add.
    expect(source).toMatch(/\bstale\b[^\n]*=\s*useTasks|,\s*stale\s*,/);
  });
});
