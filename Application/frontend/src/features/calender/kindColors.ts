import { CSSProperties } from "react";
import { EventKind } from "./types";

/** Default colour per kind, for the pickers; must match calendar.css's `--kind-color` defaults. */
export const DEFAULT_KIND_COLORS: Record<EventKind, string> = {
  lecture: "#4593d6",
  lab: "#56b39a",
  discussion: "#8a7fd4",
  midterm: "#e0685f",
  final: "#c9453c",
  deadline: "#d4af37",
  personal: "#94a3b8",
  shift: "#4fa86f",
};

/** The student's colour overrides, by kind. */
export type KindColors = Partial<Record<EventKind, string>>;

/** The colour a kind is drawn in: the student's override, else the default. */
export function kindColor(kind: EventKind, overrides: KindColors | undefined): string {
  return overrides?.[kind] ?? DEFAULT_KIND_COLORS[kind];
}

/** Inline `--kind-color` for an overridden kind; undefined leaves the stylesheet's default. */
export function kindStyle(kind: EventKind, overrides: KindColors | undefined): CSSProperties | undefined {
  const color = overrides?.[kind];
  return color ? ({ "--kind-color": color } as CSSProperties) : undefined;
}
