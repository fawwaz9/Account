import { describe, expect, it } from "vitest";
import { nowIn } from "./zonedNow";

/**
 * vitest.config.ts pins the process to America/Regina, so a test that only
 * asserted Regina would pass against the browser clock too. Each case below uses
 * a zone that differs from the process's, or it would prove nothing.
 */
describe("nowIn", () => {
  const evening = new Date("2026-10-04T01:30:00Z"); // 19:30 on the 3rd in Regina

  it("reads the day and minute in the named zone", () => {
    expect(nowIn("America/Regina", evening)).toEqual({ date: "2026-10-03", minutes: 19 * 60 + 30 });
  });

  it("follows the setting, not the machine, across midnight", () => {
    // The whole reason this exists: UTC is already the 4th.
    expect(nowIn("UTC", evening)).toEqual({ date: "2026-10-04", minutes: 90 });
  });

  it("handles a zone a day ahead", () => {
    expect(nowIn("Pacific/Kiritimati", evening)).toEqual({ date: "2026-10-04", minutes: 15 * 60 + 30 });
  });

  it("reads midnight as minute 0, not 24:00", () => {
    // hourCycle h23 -- some engines render midnight as "24" under h24.
    expect(nowIn("UTC", new Date("2026-10-04T00:00:00Z"))).toEqual({ date: "2026-10-04", minutes: 0 });
  });

  it("reads the last minute of the day as 1439", () => {
    expect(nowIn("UTC", new Date("2026-10-04T23:59:00Z")).minutes).toBe(1439);
  });

  it("falls back to the browser clock for a zone it cannot use, rather than throwing", () => {
    // The process clock is Regina, so the fallback reads the 3rd.
    expect(nowIn("Mars/Olympus", evening)).toEqual({ date: "2026-10-03", minutes: 19 * 60 + 30 });
    expect(nowIn(undefined, evening)).toEqual({ date: "2026-10-03", minutes: 19 * 60 + 30 });
  });
});
