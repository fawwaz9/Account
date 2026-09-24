// @vitest-environment jsdom
import { Suspense, lazy } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Loading from "../shared/components/Loading";

/**
 * That a route loaded on demand still arrives, and says so while it does not.
 *
 * The risk this covers is specific to splitting: `lazy()` suspends, and a route
 * that suspends with no boundary above it takes the whole app down rather than
 * showing a spinner. That failure does not exist until the first `lazy()` is
 * added, TypeScript cannot see it, and it appears only on the slow connections
 * nobody develops on -- on a fast one the chunk is there before the first
 * paint and everything looks fine.
 *
 * It exercises the same three pieces `MainLayout` wires together -- a lazy
 * element, one `Suspense`, and the shared `Loading` fallback -- against a
 * deliberately delayed import rather than the real pages, so it tests the
 * arrangement and not nine screens' worth of data fetching.
 */

function deferred() {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  return { gate, release };
}

describe("a lazily loaded route", () => {
  it("shows the fallback while the chunk is in flight, then the page", async () => {
    const { gate, release } = deferred();
    const Late = lazy(async () => {
      await gate;
      return { default: () => <p>the budget page</p> };
    });

    render(
      <MemoryRouter initialEntries={["/budget"]}>
        <Routes>
          <Route
            path="/budget"
            element={
              <Suspense fallback={<Loading label="Loading…" />}>
                <Late />
              </Suspense>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    // Before the chunk lands: the spinner, and nothing of the page.
    expect(screen.getByText("Loading…")).toBeDefined();
    expect(screen.queryByText("the budget page")).toBeNull();

    release();

    await waitFor(() => expect(screen.getByText("the budget page")).toBeDefined());
    expect(screen.queryByText("Loading…")).toBeNull();
  });

  /**
   * The fallback has to announce itself, not just spin. A person using a
   * screen reader gets nothing at all from a rotating border, so the waiting
   * state would be indistinguishable from a page that rendered empty.
   */
  it("announces the wait to a screen reader", () => {
    render(<Loading label="Loading…" />);

    // <output> carries the status role natively -- that is why it is used here
    // rather than a div with role="status".
    expect(screen.getByRole("status")).toBeDefined();
  });
});
