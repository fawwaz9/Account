/** Number formatting for display; money keeps its padding through `formatMoney` instead. */

/** Round to at most `places` decimals with trailing zeros dropped; non-finite input reads "0". */
export function trimNumber(value: number, places = 2): string {
  if (!Number.isFinite(value)) return "0";
  const factor = 10 ** places;
  // `+ 0` turns -0 back into 0, so a rounded-away negative does not read "-0".
  return String(Math.round(value * factor) / factor + 0);
}
