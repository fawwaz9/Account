// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

/** A shared computer must stop receiving someone's reminders when they sign out. */

const forgetThisDevice = vi.fn();
vi.mock("../../features/notifications/push", () => ({ forgetThisDevice: () => forgetThisDevice() }));
vi.mock("../../services/currentUserClient", () => ({
  getCurrentUser: vi.fn().mockResolvedValue({ id: "u1", preferences: {} }),
}));

const { AuthProvider, useAuth } = await import("./AuthContext");

function SignOut() {
  const { logout } = useAuth();
  return <button type="button" onClick={logout}>Sign out</button>;
}

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

it("signing out unsubscribes this browser from push", () => {
  render(<AuthProvider><SignOut /></AuthProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(forgetThisDevice).toHaveBeenCalledTimes(1);
});
