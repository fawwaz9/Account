// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import HelpTip from "./HelpTip";

/**
 * The (?) that replaces ambient explanatory text.
 *
 * Three of these assertions are the point of the component rather than details
 * of it. It must be a real button, because a hover-only explanation reaches
 * neither a touch screen nor a keyboard -- which is the whole reason the 64
 * `title` attributes already in this codebase do not solve this problem. It must
 * carry a name of its own, because "question mark" tells a screen-reader user
 * nothing and a page will have several. And it must close on Escape, because an
 * opened panel with no way back is worse than a line of muted text.
 */

afterEach(cleanup);

function mark() {
  return screen.getByRole("button", { name: "What this does" });
}

describe("HelpTip", () => {
  it("starts closed, with nothing in the DOM to read", () => {
    render(<HelpTip label="What this does">The explanation.</HelpTip>);

    expect(mark().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("The explanation.")).toBeNull();
  });

  it("is a button with a name of its own, not a punctuation mark", () => {
    render(<HelpTip label="What this does">The explanation.</HelpTip>);

    // Found by that name at all, which getByRole above already proves -- and the
    // glyph is hidden, so the name cannot be coming from the "?" itself.
    expect(mark().tagName).toBe("BUTTON");
    expect(mark().getAttribute("type")).toBe("button");
    expect(mark().querySelector('[aria-hidden="true"]')?.textContent).toBe("?");
  });

  it("opens on click and says so", () => {
    render(<HelpTip label="What this does">The explanation.</HelpTip>);

    fireEvent.click(mark());

    expect(mark().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("The explanation.")).toBeDefined();
  });

  it("closes on a second click", () => {
    render(<HelpTip label="What this does">The explanation.</HelpTip>);

    fireEvent.click(mark());
    fireEvent.click(mark());

    expect(mark().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("The explanation.")).toBeNull();
  });

  it("closes on Escape", () => {
    render(<HelpTip label="What this does">The explanation.</HelpTip>);
    fireEvent.click(mark());

    fireEvent.keyDown(mark(), { key: "Escape" });

    expect(mark().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("The explanation.")).toBeNull();
  });

  it("points the button at the panel it controls", () => {
    render(<HelpTip label="What this does">The explanation.</HelpTip>);
    fireEvent.click(mark());

    const panel = document.getElementById(mark().getAttribute("aria-controls")!);
    expect(panel).not.toBeNull();
    expect(panel!.textContent).toBe("The explanation.");
  });

  /**
   * Escape is stopped on the way up so a tip inside a dialog does not close the
   * dialog as well -- the innermost open thing should be the one that closes.
   */
  it("does not let Escape through to whatever contains it", () => {
    let reachedParent = false;
    render(
      <div onKeyDown={() => { reachedParent = true; }}>
        <HelpTip label="What this does">The explanation.</HelpTip>
      </div>,
    );
    fireEvent.click(mark());

    fireEvent.keyDown(mark(), { key: "Escape" });

    expect(reachedParent).toBe(false);
  });

  /**
   * The control for the test above. If Escape were swallowed unconditionally,
   * a closed tip would eat the keystroke that should reach the dialog around it.
   */
  it("lets Escape through when it is already closed", () => {
    let reachedParent = false;
    render(
      <div onKeyDown={() => { reachedParent = true; }}>
        <HelpTip label="What this does">The explanation.</HelpTip>
      </div>,
    );

    fireEvent.keyDown(mark(), { key: "Escape" });

    expect(reachedParent).toBe(true);
  });

  it("gives two tips on one page different panels", () => {
    render(
      <>
        <HelpTip label="What this does">First.</HelpTip>
        <HelpTip label="What that does">Second.</HelpTip>
      </>,
    );

    const ids = screen.getAllByRole("button").map((b) => b.getAttribute("aria-controls"));
    expect(new Set(ids).size).toBe(2);
  });
});
