// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Task } from "../types";

/**
 * `stale` -- loading with nothing on screen that answers the question asked.
 *
 * `loading` alone cannot drive a group's "Loading..." line, because it is also
 * true during a plain reload, when the rows already shown are still the right
 * ones; swapping them for a spinner every time something is added would only
 * make the page restless. `stale` is the narrower fact: the filter has changed
 * and the rows in state belong to the previous one. That is the moment an empty
 * message is a lie, and the only moment a group may say it is loading.
 */

/**
 * `fetchTasks` is held open so the loading window can be inspected. One pending
 * resolver per call, FIFO: `runRepeating` is awaited first, so the fetch does
 * not even exist at the moment the test asks to answer it.
 */
const pending: Array<(rows: Task[]) => void> = [];

const calls = {
  runRepeating: vi.fn(async () => undefined),
  fetchTasks: vi.fn(() => new Promise<Task[]>((resolve) => { pending.push(resolve); })),
  fetchRepeating: vi.fn(async () => []),
};

vi.mock("../api", () => calls);
vi.mock("../../../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "11111111-1111-1111-1111-111111111111" } }),
}));

const { useTasks } = await import("./useTasks");

beforeEach(() => {
  for (const fn of Object.values(calls)) fn.mockClear();
  pending.length = 0;
});

/** Let the fetch in flight answer with `rows`. */
async function answer(rows: Task[] = []) {
  await waitFor(() => expect(pending.length).toBeGreaterThan(0));
  pending.shift()!(rows);
}

describe("useTasks", () => {
  it("is stale before the first answer arrives", async () => {
    const { result } = renderHook(() => useTasks({ includeDone: false }));

    await waitFor(() => expect(result.current.loading).toBe(true));
    expect(result.current.stale).toBe(true);

    await answer();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.stale).toBe(false);
  });

  it("goes stale when the filter changes, because the rows are the old answer", async () => {
    const { result, rerender } = renderHook(
      ({ includeDone }: { includeDone: boolean }) => useTasks({ includeDone, includeArchived: includeDone }),
      { initialProps: { includeDone: false } },
    );

    await answer();
    await waitFor(() => expect(result.current.stale).toBe(false));

    // This is the reported bug: "Show completed" turns on, the refetch starts,
    // and `tasks` still holds the rows fetched without the done ones in them.
    rerender({ includeDone: true });
    await waitFor(() => expect(result.current.stale).toBe(true));

    await answer();
    await waitFor(() => expect(result.current.stale).toBe(false));
  });

  it("is NOT stale during a plain reload of the same filter", async () => {
    const { result } = renderHook(() => useTasks({ includeDone: false }));

    await answer();
    await waitFor(() => expect(result.current.stale).toBe(false));

    result.current.reload();
    await waitFor(() => expect(result.current.loading).toBe(true));
    expect(result.current.stale).toBe(false);
  });
});
