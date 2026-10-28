import { defineConfig } from "vitest/config";

/**
 * Vitest config, kept apart from vite.config.ts so tests need no build-time variables.
 * Node environment by default; TZ pinned to America/Regina.
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}", "*.test.ts"],

    // Every date in this app is a plain local date, so a suite run in UTC
    // would pass while the bug it is guarding against -- a date read one day
    // early west of Greenwich -- is exactly what cannot happen there.
    // America/Regina is UTC-6 and, unusually, observes no daylight saving, so
    // the offset is the same in January and July and no test can start
    // failing for half the year. It is also the timezone the backend's
    // completion-timing test pins, so both suites reason about one clock.
    env: { TZ: "America/Regina" },
  },
});
