// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setClockZone, today } from "../../shared/utils/dateUtils";

/**
 * The provider is what puts today() on the student's clock. A correct today()
 * that nothing ever points at the setting is the failure this guards: every
 * page would keep reading the browser's day and every test of today() would
 * still pass.
 */
const getCurrentUser = vi.fn();
vi.mock("../../services/currentUserClient", () => ({
  getCurrentUser: () => getCurrentUser(),
}));

const { AuthProvider, useAuth } = await import("./AuthContext");

/** Renders the day a page would compute, on every render. */
function Probe() {
  const { user } = useAuth();
  return <p>{user ? `signed in: ${today()}` : `signed out: ${today()}`}</p>;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-04T01:30:00Z")); // 3rd in Regina, 4th in UTC
  sessionStorage.setItem("access_token", "t");
});

afterEach(() => {
  cleanup();
  setClockZone(null);
  sessionStorage.clear();
  vi.useRealTimers();
});

describe("AuthProvider and the clock", () => {
  it("puts today() on the signed-in student's Settings zone", async () => {
    getCurrentUser.mockResolvedValue({ id: "u1", preferences: { timezone: "UTC" } });
    render(<AuthProvider><Probe /></AuthProvider>);

    // The browser's day (Regina) would read the 3rd.
    expect(await screen.findByText("signed in: 2026-10-04")).toBeTruthy();
  });

  it("follows a zone changed in Settings once the user is re-read", async () => {
    getCurrentUser.mockResolvedValue({ id: "u1", preferences: { timezone: "America/Regina" } });
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("signed in: 2026-10-03")).toBeTruthy();
    cleanup();

    getCurrentUser.mockResolvedValue({ id: "u1", preferences: { timezone: "Pacific/Kiritimati" } });
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("signed in: 2026-10-04")).toBeTruthy();
  });

  it("uses the browser's day when nobody is signed in", async () => {
    setClockZone("UTC"); // as if a previous user had left it set
    sessionStorage.clear();
    getCurrentUser.mockResolvedValue(null);
    render(<AuthProvider><Probe /></AuthProvider>);

    await waitFor(() => expect(screen.getByText("signed out: 2026-10-03")).toBeTruthy());
  });
});
