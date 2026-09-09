/**
 * One place that decides how money reads, so a balance and a ledger row can
 * never disagree about sign or decimals.
 */
export function formatMoney(amount: number, options: { signed?: boolean } = {}) {
  const formatted = Math.abs(amount).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  if (options.signed) {
    return `${amount < 0 ? "−" : "+"}$${formatted}`;
  }

  return `${amount < 0 ? "−" : ""}$${formatted}`;
}
