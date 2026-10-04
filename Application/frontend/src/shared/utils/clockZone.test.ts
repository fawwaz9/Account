import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setClockZone, today } from "./dateUtils";

/**
 * today() on the student's Settings zone.
 *
 * The process clock is pinned to America/Regina (vitest.config.ts), so the
 * moment chosen below is 19:30 on the 3rd there and already the 4th in UTC.
 * Anything that only checked Regina would pass against the browser clock too.
 */
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-04T01:30:00Z"));
});

afterEach(() => {
  setClockZone(null);
  vi.useRealTimers();
});

describe("today()", () => {
  it("reads the browser's day until a zone is known", () => {
    expect(today()).toBe("2026-10-03");
  });

  it("reads the Settings zone once one is set, across midnight", () => {
    setClockZone("UTC");
    expect(today()).toBe("2026-10-04");
  });

  it("goes back to the browser's day when the zone is cleared, as on sign-out", () => {
    setClockZone("UTC");
    setClockZone(undefined);
    expect(today()).toBe("2026-10-03");
  });

  it("falls back to the browser's day for a zone it cannot use, rather than throwing", () => {
    setClockZone("Mars/Olympus");
    expect(today()).toBe("2026-10-03");
  });
});
