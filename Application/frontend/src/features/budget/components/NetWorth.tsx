import { NetWorth as Figure } from "../types";
import { formatMoney } from "../money";

/** Props: the server's net worth, or null while loading. */
interface NetWorthProps {
  readonly figure: Figure | null;
}

/** Net worth headline, with a debt line when there is debt and any investment gain disclosed. */
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

      {/* Disclosure, not decoration. This part of the headline is not money that
          has passed through the ledger -- it is what the holdings are reckoned to
          be worth, as of whenever a reading was last recorded. */}
      {figure.investment_gain !== 0 && (
        <p className="small-text netWorthGain">
          <span>
            {figure.investment_gain < 0
              ? "Includes investment loss"
              : "Includes investment gain"}
          </span>
          <span className="netWorthGainAmount">
            {formatMoney(Math.abs(figure.investment_gain))}
          </span>
        </p>
      )}
    </section>
  );
}
