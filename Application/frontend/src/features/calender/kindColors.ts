import { CSSProperties } from "react";
import { EventKind } from "./types";

/**
 * What each kind is drawn in unless the student chose otherwise.
 *
 * Mirrors the `--kind-color` defaults in calendar.css, which is what actually
 * paints an unchanged kind; these are for the colour pickers, which need a value
 * to show. Deadline is --gold's value, because an <input type="color"> cannot
 * hold a variable.
 */
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

export type KindColors = Partial<Record<EventKind, string>>;

/** The colour a kind is drawn in: the student's, or the default. */
export function kindColor(kind: EventKind, overrides: KindColors | undefined): string {
  return overrides?.[kind] ?? DEFAULT_KIND_COLORS[kind];
}

/**
 * The inline style that applies a student's colour, or nothing at all.
 *
 * `undefined` for a kind they have not changed, so it renders from the
 * stylesheet exactly as it did before colours were customisable. An inline
 * custom property outranks the class's, which is the whole mechanism -- the
 * shared chip rules derive both the bar and the tint from `--kind-color`.
 */
export function kindStyle(kind: EventKind, overrides: KindColors | undefined): CSSProperties | undefined {
  const color = overrides?.[kind];
  return color ? ({ "--kind-color": color } as CSSProperties) : undefined;
}
