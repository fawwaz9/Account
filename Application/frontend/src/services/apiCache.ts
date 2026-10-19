/**
 * The GET cache (audit #35): a page you come back to shows what it had at once,
 * and is refetched in the background every time.
 *
 * - **Always refetched** (your call, 2026-10-18). A cached answer is shown
 *   while the same request goes out again; if the answer changed, the cache is
 *   updated and every listener is told, so the page re-reads it. Nothing waits
 *   on the network that didn't before, and nothing is trusted for long.
 * - **Any write empties it.** A POST, PATCH, PUT or DELETE clears every entry,
 *   so your own change is never shown stale: the reload after a save goes to
 *   the network, as it always did. Which reads a write touches isn't tracked
 *   -- a transaction moves the budget, the dashboard and the forecast -- so
 *   all of it goes, which is never wrong.
 * - **Five minutes at most.** An entry older than that isn't shown at all; the
 *   request waits on the network as before. A tab left open overnight never
 *   opens a page on yesterday's figures.
 * - **One user's.** Entries are dropped whenever the session token changes, so
 *   signing in as someone else on the same tab can't show the last person's.
 * - **In memory only.** Nothing is written to the browser's storage; a reload
 *   starts empty.
 *
 * Callers get a copy, never the cached object, so code that sorts or edits
 * what it was handed can't change what the next page is shown.
 */

/** Shown no older than this; older waits on the network. */
export const MAX_AGE_MS = 5 * 60_000;
/**
 * Not refetched again within this of the last answer. A change notice makes
 * every listening page re-read, and those re-reads must come from the cache
 * rather than each start another round.
 */
export const RECHECK_GAP_MS = 2_000;

interface Entry {
  data: unknown;
  /** The answer as JSON, to tell a changed answer from the same one again. */
  text: string;
  /** When the network last answered for it. */
  at: number;
}

let entries = new Map<string, Entry>();
let inflight = new Map<string, Promise<unknown>>();
// Bumped by every clear: an answer to a request sent before a write describes
// the data before it, so it must not be stored after.
let generation = 0;
let owner: string | null = null;
const listeners = new Set<() => void>();
let noticePending = false;

/** Drop everything. Every write calls this, before and after it is sent. */
export function clearApiCache(): void {
  entries = new Map();
  inflight = new Map();
  generation += 1;
}

/** Called with nothing whenever a background refetch found a changed answer. */
export function onApiRefresh(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

// One notice per task, however many answers changed in it: a page reading
// four endpoints re-reads once, not four times.
function notify() {
  if (noticePending) return;
  noticePending = true;
  setTimeout(() => {
    noticePending = false;
    for (const listener of [...listeners]) listener();
  }, 0);
}

function fromNetwork(path: string, load: () => Promise<unknown>): Promise<unknown> {
  const running = inflight.get(path);
  if (running) return running;

  const sentIn = generation;
  const promise = load()
    .then((data) => {
      if (sentIn === generation) {
        const text = JSON.stringify(data);
        const before = entries.get(path);
        entries.set(path, { data, text, at: Date.now() });
        if (before && before.text !== text) notify();
      }
      return data;
    })
    .finally(() => {
      if (inflight.get(path) === promise) inflight.delete(path);
    });
  inflight.set(path, promise);
  return promise;
}

/**
 * A GET through the cache. `token` is the session it's read for; `load` is the
 * real request. `fresh` skips the cached answer (a poll wants this minute's,
 * not the last one's) but still stores what comes back.
 */
export async function cachedGet<T>(
  path: string, token: string | null, load: () => Promise<T>, fresh = false,
): Promise<T> {
  if (token !== owner) {
    clearApiCache();
    owner = token;
  }

  const hit = entries.get(path);
  const now = Date.now();
  if (!fresh && hit && now - hit.at <= MAX_AGE_MS) {
    if (now - hit.at >= RECHECK_GAP_MS) {
      // A failed refetch keeps what's shown: the next visit tries again.
      fromNetwork(path, load).catch(() => {});
    }
    return structuredClone(hit.data) as T;
  }
  return structuredClone(await fromNetwork(path, load)) as T;
}
