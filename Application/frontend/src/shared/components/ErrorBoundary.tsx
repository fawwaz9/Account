import { Component, type ErrorInfo, type ReactNode } from "react";
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
 */

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
    console.error("Unhandled render error:", error, info.componentStack);
  }

  render() {
    const { error, componentStack } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="crashPage" role="alert">
        <div className="crashCard">
          <h1 className="crashTitle">This page stopped working</h1>
          <p className="crashBody">
            Something went wrong while drawing the page. Anything you had already
            saved is still saved &mdash; but anything half-typed on this screen is
            gone.
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
