/** In-memory GET cache: a revisit answers at once and refetches behind; any write empties it. */

/** Oldest cached answer still shown; anything older waits on the network. */
export const MAX_AGE_MS = 5 * 60_000;
/** No background refetch within this long of the last answer, so notice re-reads stay cached. */
export const RECHECK_GAP_MS = 2_000;

/** One cached GET answer. */
interface Entry {
  data: unknown;
  /** The answer as JSON, compared to spot a changed answer. */
  text: string;
  /** Epoch ms of the last network answer. */
  at: number;
}

/** Cached answers keyed by request path. */
let entries = new Map<string, Entry>();
/** Requests in flight by path, so concurrent reads share one. */
let inflight = new Map<string, Promise<unknown>>();
/** Bumped by every clear; an answer to a request sent before it is not stored. */
let generation = 0;
/** Session token the entries belong to; a different token empties the cache. */
let owner: string | null = null;
/** Callbacks told when a background refetch brings a changed answer. */
const listeners = new Set<() => void>();
/** True while a change notice is queued for this task. */
let noticePending = false;

/** Empty the cache; every write not sent with `keepCache` calls this before and after. */
export function clearApiCache(): void {
  entries = new Map();
  inflight = new Map();
  generation += 1;
}

/** Subscribe to changed-answer notices; returns the unsubscribe. */
export function onApiRefresh(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Queue one change notice per task, however many answers changed. */
function notify() {
  if (noticePending) return;
  noticePending = true;
  setTimeout(() => {
    noticePending = false;
    for (const listener of [...listeners]) listener();
  }, 0);
}

/** Run or join the request for a path; store the answer unless a clear came since. */
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
 * GET through the cache: a hit under five minutes returns a copy and refetches behind.
 * `fresh` skips the hit but still stores the answer.
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
