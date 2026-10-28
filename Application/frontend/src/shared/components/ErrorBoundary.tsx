import { Component, type ErrorInfo, type ReactNode } from "react";
import { isChunkLoadError, shouldAutoReload } from "../utils/chunkErrors";
import "../../styles/errorBoundary.css";

/** Session-storage key holding the epoch ms of the last automatic reload. */
const RELOAD_KEY = "chunk-reload-at";

/** Epoch ms of the last automatic reload; null when none is recorded or storage throws. */
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

/** Store the reload time; false when storage refuses, and then no reload is attempted. */
function recordReload(at: number): boolean {
  try {
    sessionStorage.setItem(RELOAD_KEY, String(at));
    return true;
  } catch {
    return false;
  }
}

/** The tree the boundary guards. */
type Props = { children: ReactNode };
/** The caught error and its React component stack; both null until something throws. */
type State = { error: Error | null; componentStack: string | null };

/**
 * App-wide render error boundary: a crash page offering a reload or the dashboard.
 * A route chunk lost to a deploy reloads the page once instead (see `chunkErrors`).
 */
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
