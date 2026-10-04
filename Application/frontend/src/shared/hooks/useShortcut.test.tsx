// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useShortcut } from "./useShortcut";

/**
 * The one rule every shortcut goes through: nothing fires while typing.
 *
 * Each case presses a bare "n" somewhere it must be left alone. A shortcut that
 * fired from a text field would open a form in the middle of a sentence, so
 * these are the guard, not polish.
 */

function Harness({ onFire }: { readonly onFire: () => void }) {
  useShortcut("n", onFire);
  return (
    <div>
      <input aria-label="field" />
      <textarea aria-label="notes" />
      <select aria-label="pick"><option>a</option></select>
      <div contentEditable aria-label="editable" suppressContentEditableWarning>x</div>
      <button type="button">plain</button>
    </div>
  );
}

function setup() {
  const onFire = vi.fn();
  const view = render(<Harness onFire={onFire} />);
  return { onFire, view };
}

afterEach(cleanup);

describe("useShortcut", () => {
  it("fires on a bare key pressed on the page", () => {
    const { onFire } = setup();
    fireEvent.keyDown(document.body, { key: "n" });
    expect(onFire).toHaveBeenCalledTimes(1);
  });

  it("matches the letter in either case", () => {
    const { onFire } = setup();
    fireEvent.keyDown(document.body, { key: "N", shiftKey: true });
    expect(onFire).toHaveBeenCalledTimes(1);
  });

  it("fires from a focused button, which is not typing", () => {
    const { onFire, view } = setup();
    fireEvent.keyDown(view.getByText("plain"), { key: "n" });
    expect(onFire).toHaveBeenCalledTimes(1);
  });

  it.each(["field", "notes", "pick", "editable"])("stays quiet in the %s", (label) => {
    const { onFire, view } = setup();
    fireEvent.keyDown(view.getByLabelText(label), { key: "n" });
    expect(onFire).not.toHaveBeenCalled();
  });

  it.each(["metaKey", "ctrlKey", "altKey"])("leaves the key alone with %s held", (modifier) => {
    const { onFire } = setup();
    fireEvent.keyDown(document.body, { key: "n", [modifier]: true });
    expect(onFire).not.toHaveBeenCalled();
  });

  it("stays quiet while an input method is composing", () => {
    const { onFire } = setup();
    fireEvent.keyDown(document.body, { key: "n", isComposing: true });
    expect(onFire).not.toHaveBeenCalled();
  });

  it("stays quiet while a dialog is open", () => {
    const { onFire } = setup();
    const dialog = document.createElement("div");
    dialog.setAttribute("aria-modal", "true");
    document.body.appendChild(dialog);
    try {
      fireEvent.keyDown(document.body, { key: "n" });
      expect(onFire).not.toHaveBeenCalled();
    } finally {
      dialog.remove();
    }
  });

  it("does nothing when disabled", () => {
    const onFire = vi.fn();
    function Off() {
      useShortcut("n", onFire, false);
      return null;
    }
    render(<Off />);
    fireEvent.keyDown(document.body, { key: "n" });
    expect(onFire).not.toHaveBeenCalled();
  });
});
