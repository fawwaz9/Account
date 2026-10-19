import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cachedGet, clearApiCache, MAX_AGE_MS, onApiRefresh, RECHECK_GAP_MS } from "./apiCache";

/**
 * The GET cache (audit #35): shown at once, always refetched behind, emptied by
 * any write, never older than five minutes, never another session's.
 */

const TOKEN = "token-a";

/** A request whose answers are queued: each call takes the next one. */
function server(...answers: unknown[]) {
  const load = vi.fn(async (): Promise<any> => {  // eslint-disable-line @typescript-eslint/no-explicit-any
    if (answers.length === 0) throw new Error("no answer queued");
    const next = answers.shift();
    if (next instanceof Error) throw next;
    return next;
  });
  return load;
}

/** Let pending promises and the change notice's timer run. */
async function settle() {
  await vi.advanceTimersByTimeAsync(0);
}

beforeEach(() => {
  vi.useFakeTimers();
  clearApiCache();
});
afterEach(() => {
  // A change notice still queued must fire, or it holds the next test's back.
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
});

describe("a revisit", () => {
  it("is answered from the cache at once, and refetched behind it", async () => {
    const load = server({ n: 1 }, { n: 1 });
    expect(await cachedGet("/a", TOKEN, load)).toEqual({ n: 1 });
    vi.advanceTimersByTime(RECHECK_GAP_MS);

    expect(await cachedGet("/a", TOKEN, load)).toEqual({ n: 1 });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("shows the old answer first, then the new one once the refetch lands, and says so", async () => {
    const load = server({ n: 1 }, { n: 2 });
    const changed = vi.fn();
    const stop = onApiRefresh(changed);
    await cachedGet("/a", TOKEN, load);
    vi.advanceTimersByTime(RECHECK_GAP_MS);

    expect(await cachedGet("/a", TOKEN, load)).toEqual({ n: 1 });
    await settle();
    expect(changed).toHaveBeenCalledTimes(1);
    expect(await cachedGet("/a", TOKEN, load)).toEqual({ n: 2 });
    stop();
  });

  it("says nothing when the refetch brings the same answer", async () => {
    const load = server({ n: 1 }, { n: 1 });
    const changed = vi.fn();
    const stop = onApiRefresh(changed);
    await cachedGet("/a", TOKEN, load);
    vi.advanceTimersByTime(RECHECK_GAP_MS);
    await cachedGet("/a", TOKEN, load);
    await settle();
    expect(changed).not.toHaveBeenCalled();
    stop();
  });

  it("sends one notice for several changed answers in the same moment", async () => {
    const a = server(1, 2);
    const b = server("x", "y");
    const changed = vi.fn();
    const stop = onApiRefresh(changed);
    await Promise.all([cachedGet("/a", TOKEN, a), cachedGet("/b", TOKEN, b)]);
    vi.advanceTimersByTime(RECHECK_GAP_MS);
    await Promise.all([cachedGet("/a", TOKEN, a), cachedGet("/b", TOKEN, b)]);
    await settle();
    expect(changed).toHaveBeenCalledTimes(1);
    stop();
  });

  it("is not refetched again straight after an answer, so a page re-reading on a notice costs nothing", async () => {
    const load = server({ n: 1 });
    await cachedGet("/a", TOKEN, load);
    vi.advanceTimersByTime(RECHECK_GAP_MS - 1);
    await cachedGet("/a", TOKEN, load);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("keeps the shown answer when the refetch fails", async () => {
    const load = server({ n: 1 }, new Error("offline"));
    await cachedGet("/a", TOKEN, load);
    vi.advanceTimersByTime(RECHECK_GAP_MS);
    await cachedGet("/a", TOKEN, load);
    await settle();
    expect(await cachedGet("/a", TOKEN, load)).toEqual({ n: 1 });
  });
});

describe("what is never shown", () => {
  it("an answer older than five minutes: that waits on the network", async () => {
    const load = server({ n: 1 }, { n: 2 });
    await cachedGet("/a", TOKEN, load);
    vi.advanceTimersByTime(MAX_AGE_MS + 1);
    expect(await cachedGet("/a", TOKEN, load)).toEqual({ n: 2 });
  });

  it("anything from before a write", async () => {
    const load = server({ n: 1 }, { n: 2 });
    await cachedGet("/a", TOKEN, load);
    clearApiCache();
    expect(await cachedGet("/a", TOKEN, load)).toEqual({ n: 2 });
  });

  it("an answer to a request sent before a write, even when it lands after", async () => {
    let answer!: (value: unknown) => void;
    const slow = vi.fn(() => new Promise((resolve) => { answer = resolve; }));
    const pending = cachedGet("/a", TOKEN, slow);
    clearApiCache();
    answer({ before: true });
    expect(await pending).toEqual({ before: true });
    const fresh = server({ after: true });
    expect(await cachedGet("/a", TOKEN, fresh)).toEqual({ after: true });
  });

  it("another session's answers", async () => {
    await cachedGet("/a", TOKEN, server({ who: "a" }));
    expect(await cachedGet("/a", "token-b", server({ who: "b" }))).toEqual({ who: "b" });
  });

  it("the cached object itself: a caller editing its copy changes nothing", async () => {
    const load = server({ rows: [3, 1, 2] });
    const first = await cachedGet<{ rows: number[] }>("/a", TOKEN, load);
    first.rows.sort();
    // A copy from the cache, too, not only the network's.
    const second = await cachedGet<{ rows: number[] }>("/a", TOKEN, load);
    expect(second).toEqual({ rows: [3, 1, 2] });
    second.rows.sort();
    expect(await cachedGet("/a", TOKEN, load)).toEqual({ rows: [3, 1, 2] });
  });
});

describe("requests", () => {
  it("asked for twice at once go out once", async () => {
    const load = server({ n: 1 });
    const [a, b] = await Promise.all([cachedGet("/a", TOKEN, load), cachedGet("/a", TOKEN, load)]);
    expect(a).toEqual({ n: 1 });
    expect(b).toEqual({ n: 1 });
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("marked fresh wait for this answer, not the cached one, and store it", async () => {
    const load = server([1], [1, 2], [1, 2]);
    await cachedGet("/due", TOKEN, load);
    expect(await cachedGet("/due", TOKEN, load, true)).toEqual([1, 2]);
    expect(await cachedGet("/due", TOKEN, load)).toEqual([1, 2]);
  });

  it("that fail on the first visit fail the caller, as before", async () => {
    await expect(cachedGet("/a", TOKEN, server(new Error("500")))).rejects.toThrow("500");
  });
});
