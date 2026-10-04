// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import KeyboardShortcuts, { SEQUENCE_MS } from "./KeyboardShortcuts";
import { useShortcut } from "../../shared/hooks/useShortcut";

/**
 * G then a letter to go somewhere, and ? for the list.
 *
 * The case worth pinning hardest is G T on the calendar: T alone means "today"
 * there, so the key after G has to be consumed before any page hears it.
 */

function Where() {
  return <p>at {useLocation().pathname}</p>;
}

function PageT({ onT }: { readonly onT: () => void }) {
  useShortcut("t", onT);
  return null;
}

function setup(onT = vi.fn()) {
  render(
    <MemoryRouter initialEntries={["/calendar"]}>
      <KeyboardShortcuts />
      <PageT onT={onT} />
      <input aria-label="field" />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
  return { onT };
}

function press(key: string, target: Element = document.body) {
  fireEvent.keyDown(target, { key });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("G sequences", () => {
  it("G then T goes to Tasks", () => {
    setup();
    press("g");
    press("t");
    expect(screen.getByText("at /tasks")).toBeTruthy();
  });

  it("G then T does not also fire the page's own T", () => {
    const { onT } = setup();
    press("g");
    press("t");
    expect(onT).not.toHaveBeenCalled();
  });

  it("every sidebar destination has its letter", () => {
    setup();
    for (const [key, path] of [["d", "/"], ["g", "/grades"], ["c", "/calendar"],
      ["j", "/jobs"], ["b", "/budget"], ["s", "/settings"]]) {
      press("g");
      press(key);
      expect(screen.getByText(`at ${path}`)).toBeTruthy();
    }
  });

  it("G gives up after its window, and the next key is the page's again", () => {
    vi.useFakeTimers();
    const { onT } = setup();
    press("g");
    act(() => { vi.advanceTimersByTime(SEQUENCE_MS + 1); });
    press("t");
    expect(screen.getByText("at /calendar")).toBeTruthy();
    expect(onT).toHaveBeenCalledTimes(1);
  });

  it("G typed into a field arms nothing", () => {
    const { onT } = setup();
    press("g", screen.getByLabelText("field"));
    press("t");
    expect(screen.getByText("at /calendar")).toBeTruthy();
    expect(onT).toHaveBeenCalledTimes(1);
  });
});

describe("the ? list", () => {
  it("opens on ? and closes on Escape", () => {
    setup();
    press("?");
    expect(screen.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeTruthy();
    press("Escape");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("silences page shortcuts while it is open", () => {
    const { onT } = setup();
    press("?");
    press("t");
    expect(onT).not.toHaveBeenCalled();
  });
});
