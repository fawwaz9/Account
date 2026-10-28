/** Pure checks telling a chunk lost to a deploy from a real crash; `ErrorBoundary` reloads. */

/** Each engine's message for a chunk that is no longer served, compared in lower case. */
const CHUNK_ERROR_MESSAGES = [
  // Chrome, Edge, and anything else on Blink.
  "failed to fetch dynamically imported module",
  // Firefox.
  "error loading dynamically imported module",
  // Safari.
  "importing a module script failed",
  // Vite's own preload helper, which fetches a chunk's stylesheet separately
  // and fails on its own before the module error is ever raised.
  "unable to preload css for",
];

/**
 * True when the error is a chunk-load failure from a stale deploy.
 * Kept narrow on purpose: a broader match would reload over a genuine crash.
 */
export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;

  const message = error.message.toLowerCase();
  return CHUNK_ERROR_MESSAGES.some((known) => message.includes(known));
}

/** Minimum gap between two automatic reloads, in milliseconds. */
export const RELOAD_COOLDOWN_MS = 10_000;

/**
 * True unless an automatic reload ran within the cooldown (times in epoch ms).
 * A timestamp guard, not a success flag, so a failing reload can never loop.
 */
export function shouldAutoReload(now: number, lastReloadAt: number | null): boolean {
  if (lastReloadAt === null) return true;

  return now - lastReloadAt >= RELOAD_COOLDOWN_MS;
}
