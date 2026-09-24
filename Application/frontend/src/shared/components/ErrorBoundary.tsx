import { Component, type ErrorInfo, type ReactNode } from "react";
import { isChunkLoadError, shouldAutoReload } from "../utils/chunkErrors";
import "../../styles/errorBoundary.css";

/**
 * The last thing standing between a render exception and a white screen.
 *
 * React unmounts the whole tree when a render throws and nothing catches it.
 * On your own machine that is fine -- the console has the stack and you fix it.
 * For anyone else it is a blank page with no explanation, no way to report what
 * happened, and no reason to come back. This turns that into a page that says
 * what went wrong and offers the two things that actually help.
 *
 * Still a class component in React 19: `getDerivedStateFromError` has no hook
 * equivalent, and error boundaries are the one thing hooks never replaced.
 *
 * It catches exceptions thrown while **rendering**, in lifecycle methods, and
 * in constructors below it. It does *not* catch errors in event handlers, in
 * `setTimeout`, or in rejected promises -- those never interrupt a render, so
 * React does not route them here. Those are handled where they happen, which
 * for this app means the error state each page already keeps for a failed fetch.
 *
 * **It also catches a route chunk that failed to load**, since React re-throws
 * a rejected `lazy()` import during render. That one is not a fault at all --
 * see `utils/chunkErrors.ts` -- so it is answered differently below.
 */

/** Where the last automatic reload is recorded. */
const RELOAD_KEY = "chunk-reload-at";

/**
 * Both halves wrapped, because `sessionStorage` does not merely return null
 * when it is unavailable -- reading the property *throws* where a browser is
 * set to block site data. An exception here would be thrown from inside the
 * error boundary's own handler, which is the one place in the app with nothing
 * above it to catch anything.
 *
 * Failing to read means "no record", and failing to write means the reload is
 * not attempted at all. Both fall through to the crash screen, which is exactly
 * the behaviour this app had before reloading was automatic.
 */
function readLastReload(): number | null {
  try {
    const raw = sessionStorage.getItem(RELOAD_KEY);
    if (raw === null) return null;

    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function recordReload(at: number): boolean {
  try {
    sessionStorage.setItem(RELOAD_KEY, String(at));
    return true;
  } catch {
    return false;
  }
}

type Props = { children: ReactNode };
type State = { error: Error | null; componentStack: string | null };

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, componentStack: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The component stack is the useful half and it only exists here --
    // getDerivedStateFromError is not given it.
    this.setState({ componentStack: info.componentStack ?? null });

    // A stale chunk is a deploy, not a bug: the tab is holding file names from
    // before the last release and the new build no longer serves them. Reload
    // and it is simply gone, so asking the reader to diagnose it would be
    // asking them to do something the page can do itself.
    //
    // The reload is attempted here rather than in getDerivedStateFromError
    // because that method is static and must stay pure -- React may call it
    // more than once for one error, and a side effect in it would fire twice.
    if (isChunkLoadError(error)) {
      const now = Date.now();
      if (shouldAutoReload(now, readLastReload()) && recordReload(now)) {
        window.location.reload();
        return;
      }
    }

    console.error("Unhandled render error:", error, info.componentStack);
  }

  render() {
    const { error, componentStack } = this.state;
    if (!error) return this.props.children;

    // Distinguished in the copy as well as in the handling. Someone who reaches
    // this screen despite the reload above -- a second failure inside the
    // cooldown, or a browser that will not let the page record anything -- is
    // better served by the truth than by "this page stopped working", which
    // would send them looking for a fault that is not there.
    const stale = isChunkLoadError(error);

    return (
      <div className="crashPage" role="alert">
        <div className="crashCard">
          <h1 className="crashTitle">
            {stale ? "The app was updated" : "This page stopped working"}
          </h1>
          <p className="crashBody">
            {stale ? (
              <>
                A newer version was released while this tab was open, so part of
                the old one is no longer available. Reloading picks up the new
                one &mdash; nothing you saved is affected.
              </>
            ) : (
              <>
                Something went wrong while drawing the page. Anything you had
                already saved is still saved &mdash; but anything half-typed on
                this screen is gone.
              </>
            )}
          </p>

          {/* A full reload, not a state reset. Re-rendering the same tree from
              the same props would almost always throw again immediately, which
              reads as a button that does nothing. */}
          <div className="crashActions">
            <button
              type="button"
              className="crashButton crashPrimary"
              onClick={() => window.location.reload()}
            >
              Reload the page
            </button>
            <button
              type="button"
              className="crashButton"
              onClick={() => window.location.assign("/")}
            >
              Go to the dashboard
            </button>
          </div>

          {/* Collapsed, but present. Someone reporting this can open it and
              paste the text, which is the difference between a fixable report
              and "it broke". */}
          <details className="crashDetails">
            <summary>Technical details</summary>
            <pre className="crashStack">
              {error.message || String(error)}
              {componentStack ?? ""}
            </pre>
          </details>
        </div>
      </div>
    );
  }
}
