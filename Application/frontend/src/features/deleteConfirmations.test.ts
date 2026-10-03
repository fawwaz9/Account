import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Every permanent delete asks first — and the dialog is actually wired up.
 *
 * Nine delete paths had no confirmation; enumerating the call sites found a tenth
 * (`deleteShift`) the hand audit missed. But the first version of this test only
 * looked for the identifier `DeleteConfirmModal` anywhere in the file, and an
 * `import` line satisfies that. Six of the ten sites shipped half-wired and it
 * passed: three rendered a dialog nothing opened and still deleted on one click,
 * and two had a trigger with no dialog to show.
 *
 * So this checks the wiring, in three parts:
 *
 *  1. a file that deletes must *render* a confirmation, not merely import one;
 *  2. in a file using the modal, no function that performs a delete may be wired
 *     straight to a handler prop, and no handler may call a delete api inline —
 *     that is what "deletes on one click" looks like in source;
 *  3. a rendered dialog must have something that can open it.
 *
 * Part 2 exempts the inline "Yes, delete / Keep" idiom, where the delete button
 * only renders once the confirmation is showing. Both idioms exist on purpose: the
 * modal is the default, the inline pair suits a list you are already editing.
 */

const SRC = join(__dirname, "..");

/** Actions a user can undo by clicking again, so no dialog is owed. */
const RECOVERABLE = new Set<string>([]);

/** Props that must never perform a delete. `onConfirm` is excluded deliberately:
 *  it is the dialog's own callback, which is exactly where the delete belongs. */
const HANDLER_PROPS = ["onClick", "onDelete", "onRemove", "onStop"];

/** Hooks hold the confirm state and their consumers render the dialog, so they
 *  cannot satisfy the "renders a confirmation" rule themselves. */
const PROVIDES_CONFIRM_STATE = new Set(["src/features/budget/hooks/useTransactionDelete.ts"]);

/** The body of `function name(...) {...}`, brace-matched rather than guessed at. */
function bodyOf(text: string, from: number): string {
  const open = text.indexOf("{", from);
  if (open === -1) return "";
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") {
      depth -= 1;
      if (depth === 0) return text.slice(open, i + 1);
    }
  }
  return text.slice(open);
}

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
const destructive = [
  ...new Set(
    files
      .filter((f) => f.endsWith("/api.ts"))
      .flatMap((f) => readFileSync(f, "utf8").match(/export async function (delete|clear)[A-Za-z]+/g) ?? [])
      .map((m) => m.replace("export async function ", "")),
  ),
].sort();

interface Site {
  readonly file: string;
  readonly text: string;
  readonly calls: string[];
  readonly rendersModal: boolean;
  readonly usesInline: boolean;
}

const sites: Site[] = files
  .filter((f) => !f.endsWith("/api.ts"))
  .map((file) => {
    const text = readFileSync(file, "utf8");
    return {
      file: file.replace(SRC, "src"),
      text,
      calls: destructive.filter(
        (fn) => new RegExp(`\\b${fn}\\s*\\(`).test(text) && !RECOVERABLE.has(fn),
      ),
      rendersModal: /<DeleteConfirmModal\b/.test(text),
      usesInline: /Yes, delete/.test(text),
    };
  })
  .filter((s) => s.calls.length > 0);

describe("permanent deletes ask first", () => {
  it("found the destructive calls and the sites, so the sweep is not vacuous", () => {
    expect(destructive.length).toBeGreaterThan(10);
    expect(destructive).toContain("deleteShift");
    expect(sites.length).toBeGreaterThan(10);
  });

  it("renders a confirmation at every site, not just an import", () => {
    const offenders = sites
      .filter((s) => !PROVIDES_CONFIRM_STATE.has(s.file))
      .filter((s) => !s.rendersModal && !s.usesInline)
      .map((s) => `${s.file} calls ${s.calls.join(", ")} with no confirmation rendered`);
    expect(offenders).toEqual([]);
  });

  it("never wires a delete straight to a handler", () => {
    // The failure that shipped: a dialog rendered, and the button bypassing it.
    const offenders: string[] = [];
    for (const site of sites) {
      if (!site.rendersModal) continue; // the inline idiom guards itself by rendering
      // Functions in this file whose body reaches a delete api.
      const performers = [...site.text.matchAll(/(?:async\s+)?function\s+(\w+)\s*\([^)]*\)/g)]
        .map((m) => ({ name: m[1], from: m.index! }))
        .filter(({ from }) => {
          const body = bodyOf(site.text, from);
          return destructive.some((fn) => new RegExp(`\\b${fn}\\s*\\(`).test(body));
        })
        .map(({ name }) => name);

      for (const prop of HANDLER_PROPS) {
        for (const name of performers) {
          if (new RegExp(`${prop}=\\{${name}\\}`).test(site.text)) {
            offenders.push(`${site.file}: ${prop}={${name}} deletes without opening the dialog`);
          }
        }
        // An inline handler calling the api directly is the same fault.
        for (const fn of destructive) {
          if (new RegExp(`${prop}=\\{\\(\\)\\s*=>[^}]*\\b${fn}\\s*\\(`).test(site.text)) {
            offenders.push(`${site.file}: ${prop} calls ${fn} inline, with no dialog`);
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("gives every rendered dialog something that can open it", () => {
    // The other half of the failure: a trigger setting state nothing rendered.
    const offenders: string[] = [];
    for (const site of sites) {
      for (const m of site.text.matchAll(/open=\{(\w+)\s*(?:!==\s*null)?\s*\}/g)) {
        const state = m[1];
        const setter = `set${state[0].toUpperCase()}${state.slice(1)}`;
        // Opened somewhere other than the dialog's own cancel/confirm handlers.
        const called = [...site.text.matchAll(new RegExp(`${setter}\\(([^)]*)\\)`, "g"))]
          .map((x) => x[1].trim())
          .filter((arg) => arg !== "null" && arg !== "false");
        // A setter handed to a child as the handler itself opens the dialog too.
        const byReference = new RegExp(`(?:${HANDLER_PROPS.join("|")})=\\{${setter}\\}`).test(site.text);
        if (called.length === 0 && !byReference) {
          offenders.push(`${site.file}: nothing ever calls ${setter} to open the dialog`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("names the cascade where one exists", () => {
    const fund = readFileSync(join(SRC, "features/budget/components/SinkingFunds.tsx"), "utf8");
    expect(fund).toMatch(/every transfer recorded against it/);
    const job = readFileSync(join(SRC, "features/jobs/components/JobModal.tsx"), "utf8");
    expect(job).toMatch(/every shift and paycheque/);
  });
});
