import { formatMoney } from "./money";
import { monthLabel } from "../../shared/utils/dateUtils";
import { AccountActivity } from "./types";

/**
 * Fourth tile on an investment account: its return, in one of four states.
 * The month's movement, a dated carried-forward level, the all-time first reading, or Not recorded.
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
