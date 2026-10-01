import { formatMoney } from "./money";
import { monthLabel } from "../../shared/utils/dateUtils";
import { AccountActivity } from "./types";

/**
 * What the fourth tile says on an investment account, in its four states.
 *
 * On every other kind of account that tile counts movements. Counting deposits
 * says nothing about whether a holding grew, which is the question an investment
 * account exists to answer, so here it reports the return instead.
 *
 * The four states are genuinely different claims and must not be merged into one:
 *
 * - A month with its own reading **and one before it** has a *movement* to report.
 * - A month showing an earlier month's reading has a *level* and no movement, and
 *   has to be dated, or a figure from March reads as this month's.
 * - The very first reading has a level with nothing to subtract from, so it is
 *   labelled all-time rather than attributed to the month.
 * - A month with nothing behind it at all says so. Printing `$0.00` would claim
 *   the holding was flat, which is a different statement from not knowing.
 *
 * A pure function in its own module so those four can be tested without standing
 * up the whole account page.
 */
export function returnTile(
  activity: AccountActivity,
  label: string,
): { label: string; value: string; tone?: "in" | "out" } {
  const figure = activity.investment_return;
  if (!figure) {
    return { label: `Return · ${label}`, value: "Not recorded" };
  }

  const tone = (amount: number): "in" | "out" => (amount < 0 ? "out" : "in");

  if (figure.month_gain !== null) {
    return {
      label: `Return · ${label}`,
      value: formatMoney(figure.month_gain, { signed: true }),
      tone: tone(figure.month_gain),
    };
  }

  return {
    label: figure.is_carried_forward
      ? `Return · as of ${monthLabel(figure.as_of)}`
      : "Return · all time",
    value: formatMoney(figure.difference_amount, { signed: true }),
    tone: tone(figure.difference_amount),
  };
}
