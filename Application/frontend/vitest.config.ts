import { defineConfig } from "vitest/config";

/**
 * The test runner, configured apart from `vite.config.ts` on purpose.
 *
 * That file is a function: it calls `loadEnv` and hands `VITE_API_BASE_URL` to
 * the `securityHeaders` plugin, which imports from `./src`. None of that means
 * anything in a test run -- there is no API to name and no bundle to write --
 * and wiring it in would make `npm test` fail for want of a build-time
 * variable. Keeping the two apart means the tests depend on nothing but the
 * modules they import.
 *
 * `environment: "node"` because every module tested here is pure: dates, money,
 * layout arithmetic, the CSP string. None touches the DOM, so there is no
 * jsdom, no testing-library and no setup file. Add them when a component is
 * first tested, not before.
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
