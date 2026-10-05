/**
 * Whether this tab is being used because a notification asked.
 *
 * The service worker opens a notification's page with `?from=push`. For half an
 * hour after that, this tab's visits are counted as prompted, so the usage
 * report can apply the vision's strict universe test: two rooms in a week with
 * at least one visit unprompted (account-vision.md §13.2). Half an hour, not the
 * whole tab's life: a tab left open for a week is not a week of prompted use.
 */
const KEY = "account.prompted.until";
const WINDOW_MS = 30 * 60 * 1000;

/** Read and remove the marker from the address bar, starting the window. */
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

export function isPrompted(now = Date.now()): boolean {
  try {
    const until = Number(window.sessionStorage.getItem(KEY));
    return Number.isFinite(until) && until > now;
  } catch {
    return false;
  }
}
