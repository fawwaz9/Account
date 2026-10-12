/**
 * One place that decides how money reads, so a balance and a ledger row can
 * never disagree about sign or decimals.
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

function compactAmount(amount: number) {
  if (amount >= 1000) {
    const thousands = amount / 1000;
    return `${thousands.toLocaleString(undefined, { maximumFractionDigits: thousands < 10 ? 1 : 0 })}k`;
  }

  return amount.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/**
 * A percentage, with the sign carried in the text rather than in a colour.
 *
 * Separate from `formatMoney` but deliberately beside it, because the two appear
 * next to each other -- `−8.1%` beside `−$812.40` -- and the minus has to be the
 * same character in both. It is U+2212, the real minus sign, not a hyphen.
 *
 * `signed` prints a `+` on a gain. That is not decoration: the account card shows
 * this next to a balance, and a reader has to be able to tell a gain from a loss
 * without relying on the colour it happens to be drawn in.
 *
 * Rounded to one decimal to match what the server already rounded to, rather than
 * rounding again to something different.
 */
export function formatPercent(value: number, options: { signed?: boolean } = {}) {
  const magnitude = Math.abs(value).toFixed(1);
  if (options.signed) {
    return `${value < 0 ? "−" : "+"}${magnitude}%`;
  }

  return `${value < 0 ? "−" : ""}${magnitude}%`;
}
