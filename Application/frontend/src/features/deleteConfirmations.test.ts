import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Every permanent delete asks first.
 *
 * Nine delete paths had no confirmation at all, two of which cascaded — the
 * sinking fund's own `aria-label` read "Remove {name} and its transfers", so it
 * announced the cascade and then performed it on a single click. A tenth,
 * `deleteShift`, was missed by the hand audit entirely and only turned up when the
 * call sites were enumerated instead of listed.
 *
 * That is the reason this is a test rather than a one-off sweep: the audit is of
 * **code paths, not buttons**, and a hand count missed one out of ten. A new
 * delete endpoint with no dialog now fails CI instead of shipping.
 *
 * The rule, in the owner's words: "every delete button OR INSTANCE that
 * PERMANENTLY deletes something". Recoverable actions — an archive, a soft delete,
 * a paused rule — deliberately do not need a dialog, which is why RECOVERABLE
 * below is an allowlist rather than an oversight.
 */

const SRC = join(__dirname, "..");

/** Actions a user can undo by clicking again, so no dialog is owed. */
const RECOVERABLE = new Set<string>([
  // Nothing yet. Archiving an account goes through `updateAccount`, not a delete
  // call, so it never reaches this test in the first place.
]);

/** What counts as asking first. Two idioms exist on purpose: the modal is the
 *  default, the inline "Yes, delete / Keep" pair is better inside a list you are
 *  already editing, which is why CategoriesModal uses it. */
const CONFIRMS = /DeleteConfirmModal|Yes, delete|requestDelete/;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) out.push(...walk(path));
    else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(path);
  }
  return out;
}

const files = walk(SRC);
const apiFiles = files.filter((f) => f.endsWith("/api.ts"));

/** Every destructive call the api layer exposes. */
const destructive = [
  ...new Set(
    apiFiles
      .flatMap((f) => readFileSync(f, "utf8").match(/export async function (delete|clear)[A-Za-z]+/g) ?? [])
      .map((m) => m.replace("export async function ", "")),
  ),
].sort();

describe("permanent deletes ask first", () => {
  it("finds the destructive calls at all, so the sweep below is not vacuous", () => {
    // If the api layer is ever restructured this breaks loudly rather than
    // silently passing by inspecting nothing.
    expect(destructive.length).toBeGreaterThan(10);
    expect(destructive).toContain("deleteTask");
    expect(destructive).toContain("deleteShift");
  });

  it("has a dialog behind every call site", () => {
    const offenders: string[] = [];

    for (const file of files) {
      if (file.endsWith("/api.ts")) continue;
      const text = readFileSync(file, "utf8");
      const called = destructive.filter(
        (fn) => new RegExp(`\\b${fn}\\s*\\(`).test(text) && !RECOVERABLE.has(fn),
      );
      if (called.length === 0) continue;
      if (CONFIRMS.test(text)) continue;
      offenders.push(`${file.replace(SRC, "src")} calls ${called.join(", ")}`);
    }

    expect(offenders, "a permanent delete with no confirmation").toEqual([]);
  });

  it("names the cascade where one exists", () => {
    // Two deletes take other rows with them. The dialog has to say so — the whole
    // reason the fund was the sharp one is that its label said it and the UI did
    // not ask.
    const fund = readFileSync(join(SRC, "features/budget/components/SinkingFunds.tsx"), "utf8");
    expect(fund).toMatch(/every transfer recorded against it/);

    const job = readFileSync(join(SRC, "features/jobs/components/JobModal.tsx"), "utf8");
    expect(job).toMatch(/every shift and paycheque/);
  });
});
