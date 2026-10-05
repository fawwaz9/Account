// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

/**
 * The in-app announcer and push together: a reminder already pushed to the
 * person's devices still shows in the banner, but is not announced a second
 * time as a system notification.
 */

const fetchDueReminders = vi.fn();
vi.mock("../api", () => ({
  fetchDueReminders: (...a: unknown[]) => fetchDueReminders(...a),
  dismissReminder: vi.fn(),
}));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import { useReminders } from "./useReminders";

const shown: Array<{ title: string; tag?: string }> = [];

beforeEach(() => {
  shown.length = 0;
  class FakeNotification {
    static permission = "granted";
    constructor(title: string, options?: { tag?: string }) {
      shown.push({ title, tag: options?.tag });
    }
  }
  vi.stubGlobal("Notification", FakeNotification);
});
afterEach(() => vi.unstubAllGlobals());

it("announces only the reminders no device has received", async () => {
  fetchDueReminders.mockResolvedValue([
    { id: "r1", title: "pushed already", pushed_at: "2026-10-07T12:00:00", course_code: null, notes: null },
    { id: "r2", title: "not pushed", pushed_at: null, course_code: null, notes: null },
  ]);

  const { result } = renderHook(() => useReminders());

  await waitFor(() => expect(result.current.due).toHaveLength(2));
  expect(shown).toEqual([{ title: "not pushed", tag: "reminder-r2" }]);
});
