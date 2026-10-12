// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The header. On a phone it is the owner's sketch: "Account", the profile icon
 * (the way to Settings, and so to signing out), and the omnibox on the home
 * screen only. The desktop header is unchanged.
 */

const logout = vi.fn();
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", name: "Sample Student" }, logout }),
}));
vi.mock("../../features/omnibox/Omnibox", () => ({ default: () => <div data-testid="omnibox" /> }));

import Topbar from "./Topbar";

const original = window.matchMedia;
afterEach(() => { cleanup(); window.matchMedia = original; });

function onScreen(phone: boolean) {
  window.matchMedia = vi.fn(() => ({
    matches: phone, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

function showAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><Topbar /></MemoryRouter>);
}

describe("on a phone", () => {
  it("shows the omnibox on the home screen", () => {
    onScreen(true);
    showAt("/");
    expect(screen.queryByTestId("omnibox")).not.toBeNull();
  });

  it("leaves it off every other page", () => {
    onScreen(true);
    showAt("/tasks");
    expect(screen.queryByTestId("omnibox")).toBeNull();
  });

  it("goes to Settings from the profile icon", () => {
    onScreen(true);
    showAt("/tasks");
    const profile = screen.getByRole("link", { name: "Profile and settings" });
    expect(profile.getAttribute("href")).toBe("/settings");
    expect(profile.querySelector(".appIcon")).not.toBeNull();
  });

  it("has no Sign out and no name, which live in Settings instead", () => {
    onScreen(true);
    showAt("/");
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
    expect(screen.queryByText("Sample Student")).toBeNull();
  });
});

describe("on a desktop", () => {
  it("keeps the omnibox on every page, with the name and Sign out", () => {
    onScreen(false);
    showAt("/tasks");
    expect(screen.queryByTestId("omnibox")).not.toBeNull();
    expect(screen.getByText("Sample Student")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Profile and settings" })).toBeNull();
  });
});
