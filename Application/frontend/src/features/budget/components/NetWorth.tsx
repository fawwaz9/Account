import { NetWorth as Figure } from "../types";
import { formatMoney } from "../money";

interface NetWorthProps {
  readonly figure: Figure | null;
}

/**
 * What you have, less what you owe.
 *
 * This replaces a plain `Total:` that summed every balance, which counted a
 * credit card as though it were savings and money someone else was holding as
 * though it were in your pocket.
 *
 * The debt line is shown only when there is debt, and accounts toggled out of
 * the total appear on neither line -- money owed *to* you is not money you owe,
 * and merging the two would add opposites.
 */
export default function NetWorth({ figure }: NetWorthProps) {
  if (!figure) return null;

  const under = figure.net_worth < 0;

  return (
    <section className={`netWorthBlock${under ? " netWorthBlockUnder" : ""}`} aria-label="Net worth">
      <div className="netWorthHead">
        <span className="small-text muted netWorthLabel">
          {under ? "In the red" : "Net worth"}
        </span>
      </div>

      <span className="netWorthHeadline">{formatMoney(figure.net_worth)}</span>

      {figure.debt_total > 0 && (
        <p className="small-text netWorthDebt">
          <span>Debt</span>
          <span className="netWorthDebtAmount">{formatMoney(figure.debt_total)}</span>
        </p>
      )}
    </section>
  );
}
