import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { DEFAULT_KIND_COLORS, kindColor, kindStyle } from "./kindColors";
import { EVENT_KIND_LABELS } from "./types";

describe("kind colours", () => {
  it("leaves an unchanged kind to the stylesheet entirely", () => {
    // No inline style means it renders exactly as it did before this existed.
    expect(kindStyle("lecture", {})).toBeUndefined();
    expect(kindStyle("lecture", undefined)).toBeUndefined();
  });

  it("applies a chosen colour through the custom property", () => {
    expect(kindStyle("lecture", { lecture: "#123456" })).toEqual({ "--kind-color": "#123456" });
  });

  it("does not let one kind's colour leak onto another", () => {
    expect(kindStyle("lab", { lecture: "#123456" })).toBeUndefined();
  });

  it("falls back to the default for the picker", () => {
    expect(kindColor("lab", { lecture: "#123456" })).toBe(DEFAULT_KIND_COLORS.lab);
    expect(kindColor("lecture", { lecture: "#123456" })).toBe("#123456");
  });

  it("has a default for every kind the calendar knows", () => {
    expect(Object.keys(DEFAULT_KIND_COLORS).sort()).toEqual(Object.keys(EVENT_KIND_LABELS).sort());
  });

  it("agrees with the defaults calendar.css actually paints", () => {
    // Two copies of eight colours will drift unless something compares them.
    const css = readFileSync(join(__dirname, "../../styles/calendar.css"), "utf8");
    for (const [kind, hex] of Object.entries(DEFAULT_KIND_COLORS)) {
      const rule = css.match(new RegExp(`\\.calChip-${kind}\\s*\\{[^}]*--kind-color:\\s*([^;]+);`));
      expect(rule, `no --kind-color for .calChip-${kind}`).not.toBeNull();
      const value = rule![1].trim();
      // Deadline paints with the theme's gold so it follows any theme change.
      expect(value === hex || (kind === "deadline" && value === "var(--gold)"), `${kind}: ${value} vs ${hex}`).toBe(true);
    }
  });
});
