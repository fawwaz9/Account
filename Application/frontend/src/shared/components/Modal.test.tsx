// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import Modal from "./Modal";

/**
 * Every dialog has a visible way out (owner, 2026-11-07): the shell draws a × on each one,
 * and no dialog is built outside the shell, where it could be left without one.
 */

afterEach(cleanup);

/** Every .tsx under src, tests left out. */
function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return path.endsWith(".tsx") && !path.endsWith(".test.tsx") ? [path] : [];
  });
}

describe("Modal", () => {
  it("draws a × that closes the dialog", () => {
    const onClose = vi.fn();
    render(<Modal title="Edit grade" onClose={onClose}><p>body</p></Modal>);
    const close = screen.getByRole("button", { name: "Close dialog" });
    expect(close.textContent).toBe("×");
    fireEvent.click(close);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("still closes on Escape", () => {
    const onClose = vi.fn();
    render(<Modal title="Edit grade" onClose={onClose}><p>body</p></Modal>);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("is the only place a dialog is built", () => {
    const src = join(__dirname, "../..");
    const builders = sources(src)
      .filter((path) => /role="dialog"|role="alertdialog"|aria-modal/.test(readFileSync(path, "utf8")))
      .map((path) => relative(src, path));
    expect(builders).toEqual(["shared/components/Modal.tsx"]);
  });
});
