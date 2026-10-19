// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { useEffect, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { del, get, patch, post, put } from "./apiClient";
import { clearApiCache, RECHECK_GAP_MS } from "./apiCache";
import { runRecurring } from "../features/budget/api";
import { fetchDueReminders, runRepeating } from "../features/tasks/api";
import { useApiRefresh } from "../shared/hooks/useApiRefresh";

/** The cache as the app uses it (audit #35): every GET through it, every write clearing it. */

const fetchMock = vi.fn();

function answer(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

/** Answers GET /thing with the queued bodies in turn, and any write with `write`. */
function serve(gets: unknown[], write: unknown = {}) {
  fetchMock.mockImplementation((_url: string, init: RequestInit) =>
    init.method === "GET" ? answer(gets.shift()) : answer(write));
}

const gets = () => fetchMock.mock.calls.filter(([, init]) => init.method === "GET").length;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
  vi.stubGlobal("fetch", fetchMock);
  sessionStorage.setItem("access_token", "t1");
  clearApiCache();
});
afterEach(() => {
  cleanup();
  // A change notice still queued must fire, or it holds the next test's back.
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  sessionStorage.clear();
});

describe("reads", () => {
  it("come from the cache on a revisit, refetched behind", async () => {
    serve([{ v: 1 }, { v: 1 }]);
    await get("thing");
    vi.advanceTimersByTime(RECHECK_GAP_MS);
    expect(await get("thing")).toEqual({ v: 1 });
    expect(gets()).toBe(2);
  });
});

describe("writes", () => {
  for (const [name, write] of [
    ["POST", () => post("thing", {})], ["PATCH", () => patch("thing", {})],
    ["PUT", () => put("thing", {})], ["DELETE", () => del("thing")],
  ] as const) {
    it(`${name} empties it, so the reload after a save waits for the new answer`, async () => {
      serve([{ v: 1 }, { v: 2 }]);
      await get("thing");
      await write();
      expect(await get("thing")).toEqual({ v: 2 });
    });
  }

  it("empty it even when they fail", async () => {
    await get("thing").catch(() => undefined);
    fetchMock.mockImplementation((_url: string, init: RequestInit) =>
      init.method === "GET" ? answer({ v: 1 }) : Promise.resolve(new Response("{}", { status: 500 })));
    await get("thing");
    await expect(post("thing", {})).rejects.toThrow();
    fetchMock.mockImplementation(() => answer({ v: 2 }));
    expect(await get("thing")).toEqual({ v: 2 });
  });
});

describe("the catch-up runs on every Budget and Tasks load", () => {
  for (const [name, run] of [["recurring payments", runRecurring], ["repeating tasks", runRepeating]] as const) {
    it(`(${name}) keep the cache when they wrote nothing`, async () => {
      serve([{ v: 1 }], { created: 0, transactions: [], tasks: [], skipped: [] });
      await get("thing");
      await run("u1");
      expect(await get("thing")).toEqual({ v: 1 });
      expect(gets()).toBe(1);
    });

    it(`(${name}) empty it when they wrote something`, async () => {
      serve([{ v: 1 }, { v: 2 }], { created: 1, transactions: [], tasks: [], skipped: [] });
      await get("thing");
      await run("u1");
      expect(await get("thing")).toEqual({ v: 2 });
    });
  }
});

describe("due reminders", () => {
  it("are always this poll's answer: reading them marks them surfaced", async () => {
    fetchMock.mockImplementationOnce(() => answer([])).mockImplementationOnce(() => answer([{ id: "r1" }]));
    await fetchDueReminders("u1");
    expect(await fetchDueReminders("u1")).toEqual([{ id: "r1" }]);
  });
});

describe("a page", () => {
  function Thing() {
    const [value, setValue] = useState<number | null>(null);
    const load = async () => setValue((await get<{ v: number }>("thing")).v);
    useEffect(() => { void load(); }, []);  // eslint-disable-line react-hooks/exhaustive-deps
    useApiRefresh(load);
    return <p>value {value ?? "none"}</p>;
  }

  it("catches up when the background refetch brings something new", async () => {
    serve([{ v: 1 }, { v: 2 }]);
    await get("thing");
    vi.advanceTimersByTime(RECHECK_GAP_MS);
    render(<Thing />);
    // Reading a response body takes a few turns; let them all run.
    for (let i = 0; i < 10; i += 1) await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByText("value 2")).toBeTruthy();
    // The catch-up read came from the cache: two GETs in all, not three.
    expect(gets()).toBe(2);
  });
});
