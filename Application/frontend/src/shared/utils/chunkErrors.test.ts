import { describe, expect, it } from "vitest";
import {
  RELOAD_COOLDOWN_MS,
  isChunkLoadError,
  shouldAutoReload,
} from "./chunkErrors";

/**
 * These guard the one failure that route splitting introduced: a tab open
 * across a deploy asking for a chunk that is no longer served. Getting the
 * detection too narrow shows a crash screen for a routine deploy; getting it
 * too wide reloads the page on top of a genuine bug, which hides the bug and
 * loses whatever the person had half-typed.
 */
describe("isChunkLoadError", () => {
  /**
   * Four messages for one failure, because no browser agrees on the wording
   * and none of it is standardised. Matching only Chrome's -- the one a
   * developer sees -- would leave every Firefox and Safari user with a crash
   * screen after each deploy, which is precisely the group nobody tests as.
   */
  it("recognises the message each browser actually produces", () => {
    expect(isChunkLoadError(new Error(
      "Failed to fetch dynamically imported module: https://x/assets/Budget-a1b2.js",
    ))).toBe(true);

    expect(isChunkLoadError(new Error(
      "error loading dynamically imported module",
    ))).toBe(true);

    expect(isChunkLoadError(new Error(
      "Importing a module script failed.",
    ))).toBe(true);

    expect(isChunkLoadError(new Error(
      "Unable to preload CSS for /assets/Budget-c3d4.css",
    ))).toBe(true);
  });

  /**
   * The load-bearing negative, and the reason the match list is phrases rather
   * than something looser like "failed to fetch". If an ordinary crash matched
   * here the page would reload itself instead of reporting the fault, turning
   * a bug with a stack trace into a flicker nobody can describe.
   */
  it("does not match an ordinary crash", () => {
    expect(isChunkLoadError(new TypeError("x is not a function"))).toBe(false);
    expect(isChunkLoadError(new Error("Could not load your budget"))).toBe(false);
    expect(isChunkLoadError(new Error("Failed to fetch"))).toBe(false);
  });

  it("handles a thrown value that is not an Error at all", () => {
    expect(isChunkLoadError("Failed to fetch dynamically imported module")).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
    expect(isChunkLoadError(undefined)).toBe(false);
  });
});

describe("shouldAutoReload", () => {
  it("allows the first reload", () => {
    expect(shouldAutoReload(1_000_000, null)).toBe(true);
  });

  /**
   * The guarantee that matters: never twice in a row. If a reload does not fix
   * the problem, the second failure must reach the crash screen rather than
   * start a loop on a page offering nothing to click.
   */
  it("refuses a second reload inside the cooldown", () => {
    const now = 1_000_000;

    expect(shouldAutoReload(now, now)).toBe(false);
    expect(shouldAutoReload(now, now - 1)).toBe(false);
    expect(shouldAutoReload(now, now - (RELOAD_COOLDOWN_MS - 1))).toBe(false);
  });

  /**
   * And the other half: a deploy next week must still be able to reload. A
   * guard that never reopened would be a one-reload-per-session rule, which
   * looks identical in a test written only for the clause above.
   */
  it("allows another reload once the cooldown has passed", () => {
    const now = 1_000_000;

    expect(shouldAutoReload(now, now - RELOAD_COOLDOWN_MS)).toBe(true);
    expect(shouldAutoReload(now, now - 60_000)).toBe(true);
  });
});
