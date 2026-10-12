// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The omnibox's how-to. On a phone it is behind a "?" after File (the owner's
 * sketch: "shows how to use omnibox, no text"); on a desktop the line under the
 * box stays.
 */

vi.mock("../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));
vi.mock("./api", () => ({ previewLine: vi.fn(), fileLine: vi.fn() }));

import Omnibox from "./Omnibox";

const original = window.matchMedia;
afterEach(() => { cleanup(); window.matchMedia = original; });

function onScreen(phone: boolean) {
  window.matchMedia = vi.fn(() => ({
    matches: phone, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

function show() {
  return render(<MemoryRouter><Omnibox /></MemoryRouter>);
}

describe("on a phone", () => {
  it("has no hint line under the box", () => {
    onScreen(true);
    show();
    expect(screen.queryByText(/A mark goes to Grades/)).toBeNull();
  });

  it("explains itself behind the question mark", () => {
    onScreen(true);
    show();
    const mark = screen.getByRole("button", { name: "How to use this box" });
    expect(screen.queryByRole("note")).toBeNull();
    fireEvent.click(mark);
    const note = screen.getByRole("note");
    expect(note.textContent).toMatch(/goes to Grades/);
    expect(note.textContent).toMatch(/to Budget/);
    expect(note.textContent).toMatch(/to Tasks/);
  });
});

describe("on a desktop", () => {
  it("keeps the hint line, and no question mark", () => {
    onScreen(false);
    show();
    expect(screen.getByText(/A mark goes to Grades/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "How to use this box" })).toBeNull();
  });
});
