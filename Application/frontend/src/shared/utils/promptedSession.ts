/** Marks this tab's visits as push-prompted for 30 minutes after a `?from=push` open. */

/** Session-storage key holding the epoch ms when the prompted window ends. */
const KEY = "account.prompted.until";
/** How long visits count as prompted after a notification opened the tab, in ms. */
const WINDOW_MS = 30 * 60 * 1000;

/** Start the prompted window if the URL carries `from=push`, then strip it from the address. */
export function takePromptedMarker(now = Date.now()): void {
  const url = new URL(window.location.href);
  if (url.searchParams.get("from") !== "push") return;
  try {
    window.sessionStorage.setItem(KEY, String(now + WINDOW_MS));
  } catch {
    // Storage refused: the visit counts as unprompted. An overcount of
    // unprompted use is the cost, and it is small.
  }
  url.searchParams.delete("from");
  window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
}

/** True while this tab is inside a prompted window; false if storage is unreadable. */
export function isPrompted(now = Date.now()): boolean {
  try {
    const until = Number(window.sessionStorage.getItem(KEY));
    return Number.isFinite(until) && until > now;
  } catch {
    return false;
  }
}
