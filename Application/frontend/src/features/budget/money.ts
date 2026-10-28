/**
 * Format dollars as text with a real minus sign, U+2212.
 * `signed` adds + to gains, `compact` abbreviates thousands for axes, `whole` rounds first.
 */
export function formatMoney(
  amount: number,
  options: { signed?: boolean; compact?: boolean; whole?: boolean } = {}
) {
  // Whole dollars: the phone dashboard's figures are a glance, and the owner's
  // sketch rounds them. Rounded before the sign is chosen, so -$0.40 reads as
  // $0 rather than as a minus sign in front of nothing.
  if (options.whole) amount = Math.round(amount);

  // Chart axes have no room for cents, and a four-figure tick with two
  // decimals collides with its neighbour.
  const formatted = options.compact
    ? compactAmount(Math.abs(amount))
    : Math.abs(amount).toLocaleString(undefined, {
        minimumFractionDigits: options.whole ? 0 : 2,
        maximumFractionDigits: options.whole ? 0 : 2,
      });

  if (options.signed) {
    return `${amount < 0 ? "−" : "+"}$${formatted}`;
  }

  return `${amount < 0 ? "−" : ""}$${formatted}`;
}

/** Whole-dollar magnitude, with thousands as k to one decimal under 10k. */
function compactAmount(amount: number) {
  if (amount >= 1000) {
    const thousands = amount / 1000;
    return `${thousands.toLocaleString(undefined, { maximumFractionDigits: thousands < 10 ? 1 : 0 })}k`;
  }

  return amount.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/** Format a percent to one decimal with the same minus sign; `signed` adds + to gains. */
export function formatPercent(value: number, options: { signed?: boolean } = {}) {
  const magnitude = Math.abs(value).toFixed(1);
  if (options.signed) {
    return `${value < 0 ? "−" : "+"}${magnitude}%`;
  }

  return `${value < 0 ? "−" : ""}${magnitude}%`;
}
