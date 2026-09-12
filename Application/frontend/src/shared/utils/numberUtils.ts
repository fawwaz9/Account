/**
 * Numbers for reading, not for accounting.
 *
 * `toFixed(2)` pads every value to two decimals, so a category worth exactly 20
 * marks rendered "18.00/20" — two zeros carrying no information, on a strip
 * where most values are whole. Money is the exception and keeps its padding;
 * see formatMoney.
 */

/**
 * At most `places` decimals, with trailing zeros dropped.
 *
 *   18      -> "18"
 *   2.5     -> "2.5"
 *   2.333.. -> "2.33"
 *
 * Rounding through an integer rather than `toFixed` also clears the float noise
 * that makes 0.1 + 0.2 print as 0.30000000000000004.
 */
export function trimNumber(value: number, places = 2): string {
  if (!Number.isFinite(value)) return "0";
  const factor = 10 ** places;
  // `+ 0` turns -0 back into 0, so a rounded-away negative does not read "-0".
  return String(Math.round(value * factor) / factor + 0);
}
