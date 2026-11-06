import { Grade } from "./types";

/** How far a split's total may sit from the category's weight; the server's tolerance. */
export const SPLIT_TOLERANCE = 0.01;

/** Whether a category's weight is split between its items, rather than shared evenly. */
export function isSplit(items: readonly Pick<Grade, "subcategory_weight">[]): boolean {
  return items.some((item) => item.subcategory_weight !== null && item.subcategory_weight !== undefined);
}

/** A number to 2 places, without the float noise that 0.1 + 0.2 leaves behind. */
export function toCents(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * `total` shared evenly between `count` items, to 2 places, adding up exactly: the cent or
 * so that rounding leaves over goes to the first item.
 */
export function evenSplit(total: number, count: number): number[] {
  if (count <= 0) return [];
  const each = toCents(total / count);
  const shares = Array.from({ length: count }, () => each);
  shares[0] = toCents(shares[0] + total - each * count);
  return shares;
}

/** Whether shares add up to a category's weight, within the server's tolerance. */
export function addsUp(shares: readonly number[], weight: number): boolean {
  return Math.abs(toCents(shares.reduce((sum, share) => sum + share, 0)) - weight) <= SPLIT_TOLERANCE;
}

/** The items at 0% of a split category: they count for nothing until the split changes. */
export function atZero(items: readonly Grade[]): Grade[] {
  return isSplit(items) ? items.filter((item) => !item.subcategory_weight) : [];
}
