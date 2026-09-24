/**
 * Telling "the app was updated under you" apart from "the app is broken".
 *
 * Routes are loaded on demand, so `index.html` names chunk files by content
 * hash. A tab left open across a deploy still holds the old names, and the new
 * deploy no longer serves them -- so the next route click fails on a file that
 * existed when the page was opened. Nothing is wrong with the app or the data;
 * the person is simply holding yesterday's map.
 *
 * Before splitting this could not happen: the whole app arrived in one file, so
 * every route was already in memory. It is the one new failure the split
 * introduces, which is why it gets its own module and its own tests rather than
 * a condition buried in the error boundary.
 *
 * Both functions here are pure so they can be tested without a DOM. The side
 * effect they gate -- reloading the page -- lives in `ErrorBoundary`.
 */

/**
 * The same failure, worded four ways.
 *
 * Every browser writes its own message and none of them is standardised, so
 * matching one engine's phrasing would leave the other two showing a crash
 * screen for a routine deploy. Compared case-insensitively, since the
 * capitalisation differs between them too.
 *
 * Worth knowing: the obvious word for that comparison, written as one word,
 * is also a Tailwind utility. Tailwind scans source files for candidate class
 * names and cannot tell a comment from markup, so using it here added a real
 * (and entirely unused) text-transform rule to the production stylesheet. A
 * comment changed the CSS. Hence the roundabout wording above.
 */
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
 * Is this a chunk that is no longer being served, rather than a real fault?
 *
 * Deliberately narrow. Anything broader -- matching "failed to fetch", say --
 * would swallow a genuine crash and reload the page on top of it, turning a
 * reportable bug into a flicker nobody can describe. A test asserts that an
 * ordinary `TypeError` does not match, because that is the guarantee that
 * keeps this from becoming a blanket reload.
 */
export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;

  const message = error.message.toLowerCase();
  return CHUNK_ERROR_MESSAGES.some((known) => message.includes(known));
}

/** How long to wait before a second automatic reload is allowed. */
export const RELOAD_COOLDOWN_MS = 10_000;

/**
 * May the page reload itself right now?
 *
 * The guard is a timestamp rather than a "did the reload work" flag, and that
 * choice is the whole safety of this feature. A flag needs a success signal to
 * clear it, and if that signal is ever missed the page reloads, fails, reloads
 * again -- a loop with no way out, on a screen offering nothing to click. A
 * timestamp needs no clearing at all: a failure inside the window simply falls
 * through to the ordinary crash screen, and a stale value left behind is
 * harmless.
 *
 * So the worst case is one wasted reload, and never two in a row.
 */
export function shouldAutoReload(now: number, lastReloadAt: number | null): boolean {
  if (lastReloadAt === null) return true;

  return now - lastReloadAt >= RELOAD_COOLDOWN_MS;
}
