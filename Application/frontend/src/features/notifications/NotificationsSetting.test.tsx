// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The Settings control. The browser APIs are mocked away (jsdom has none of
 * them); what is pinned is that every press is acknowledged and that the cases
 * which have to be read first replace the button instead of letting it fail.
 */

const push = {
  pushStatus: vi.fn(),
  thisDeviceIsOn: vi.fn(),
  pushSupported: vi.fn(() => true),
  needsHomeScreen: vi.fn(() => false),
  turnOn: vi.fn(),
  turnOff: vi.fn(),
  sendTestPush: vi.fn(),
};

vi.mock("./push", async () => {
  class PermissionRefused extends Error {}
  return {
    PermissionRefused,
    pushStatus: (...a: unknown[]) => push.pushStatus(...a),
    thisDeviceIsOn: () => push.thisDeviceIsOn(),
    pushSupported: () => push.pushSupported(),
    needsHomeScreen: () => push.needsHomeScreen(),
    turnOn: (...a: unknown[]) => push.turnOn(...a),
    turnOff: (...a: unknown[]) => push.turnOff(...a),
    sendTestPush: (...a: unknown[]) => push.sendTestPush(...a),
  };
});

import NotificationsSetting from "./NotificationsSetting";
import { PermissionRefused } from "./push";

const ready = { available: true, public_key: "BKEY", devices: 0 };

beforeEach(() => {
  Object.values(push).forEach((fn) => fn.mockReset());
  push.pushSupported.mockReturnValue(true);
  push.needsHomeScreen.mockReturnValue(false);
  push.pushStatus.mockResolvedValue(ready);
  push.thisDeviceIsOn.mockResolvedValue(false);
});
afterEach(cleanup);

describe("NotificationsSetting", () => {
  it("offers to turn on, and says so when it has", async () => {
    push.turnOn.mockResolvedValue(undefined);
    render(<NotificationsSetting userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Turn on for this device" }));
    expect(push.turnOn).toHaveBeenCalledWith("u1", "BKEY");
    expect(await screen.findByText(/even with the app closed/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Turn off" })).toBeTruthy();
  });

  it("says plainly when the browser refuses permission", async () => {
    push.turnOn.mockRejectedValue(new PermissionRefused("blocked"));
    render(<NotificationsSetting userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Turn on for this device" }));
    expect(await screen.findByText(/blocking notifications for this site/)).toBeTruthy();
  });

  it("acknowledges a test send and a turn-off", async () => {
    push.thisDeviceIsOn.mockResolvedValue(true);
    push.sendTestPush.mockResolvedValue({ sent: 1 });
    push.turnOff.mockResolvedValue(undefined);
    render(<NotificationsSetting userId="u1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Send a test" }));
    expect(await screen.findByText(/should arrive within a few seconds/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Turn off" }));
    expect(await screen.findByText("Off for this device.")).toBeTruthy();
    expect(push.turnOff).toHaveBeenCalledWith("u1");
  });

  it("on an iPhone tab, says to add it to the Home Screen instead of offering a button", async () => {
    push.needsHomeScreen.mockReturnValue(true);
    render(<NotificationsSetting userId="u1" />);
    expect(await screen.findByText(/add Account to your Home Screen/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Turn on/ })).toBeNull();
  });

  it("says the server is not set up rather than offering something that would fail", async () => {
    push.pushStatus.mockResolvedValue({ available: false, public_key: null, devices: 0 });
    render(<NotificationsSetting userId="u1" />);
    expect(await screen.findByText("Not set up on the server yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Turn on/ })).toBeNull();
  });

  it("says a failed check failed, instead of 'Checking…' forever or 'not set up'", async () => {
    push.pushStatus.mockRejectedValue(new Error("500"));
    render(<NotificationsSetting userId="u1" />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/Couldn't check notifications/);
    expect(screen.queryByText("Checking…")).toBeNull();
    expect(screen.queryByText("Not set up on the server yet.")).toBeNull();
  });
});
