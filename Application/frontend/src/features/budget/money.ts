/**
 * One place that decides how money reads, so a balance and a ledger row can
 * never disagree about sign or decimals.
 */
export function formatMoney(
  amount: number,
  options: { signed?: boolean; compact?: boolean } = {}
) {
  // Chart axes have no room for cents, and a four-figure tick with two
  // decimals collides with its neighbour.
  const formatted = options.compact
    ? compactAmount(Math.abs(amount))
    : Math.abs(amount).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
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
