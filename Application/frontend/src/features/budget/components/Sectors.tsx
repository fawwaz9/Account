import { Link } from "react-router-dom";
import { Account, InvestmentReturn } from "../types";
import { formatMoney, formatPercent } from "../money";
import { monthLabel } from "../../../shared/utils/dateUtils";

interface SectorsProps {
  readonly accounts: readonly Account[];
  readonly onEdit: (account: Account) => void;
  readonly onAdd: () => void;
}

/** The pots money sits in, with what each currently holds. */
const KIND_LABELS: Record<string, string> = {
  spending: "Spending",
  savings: "Savings",
  investment: "Investment",
  emergency: "Emergency",
  other: "Other",
  debt: "Debt",
};

/**
 * The return, in words, for anyone who cannot see the figure beside the balance.
 *
 * Always dated. The card shows the latest reading there is, which may have been
 * taken months ago, and "up 3.2%" with no date invites reading it as today's.
 */
function returnInWords(figure: InvestmentReturn, percent: number) {
  const direction = percent < 0 ? "down" : "up";
  // The magnitude, because "down" already carries the sign. Passing the signed
  // value would read "down −8.1%", a double negative that says the opposite of
  // what it means to anyone parsing it literally.
  return (
    `${direction} ${formatPercent(Math.abs(percent))} on what you put in, ` +
    `as of ${monthLabel(figure.as_of)}`
  );
}

/**
 * What the card's headline figure is: for an investment account with a reading,
 * what the holding is worth; for everything else, the ledger balance.
 *
 * The ledger balance alone could not be the headline once recorded gain reached
 * net worth, because then adding up the cards would never reach the total above
 * them -- and this component's own comment warns that two totals on one page
 * will sooner or later disagree in front of you. It did. This closes it.
 *
 * `balance` plus the level, because the level is market minus ledger by
 * definition. There is a backend test asserting those two stay addable.
 */
function worthOf(account: Account) {
  return account.investment_return
    ? account.balance + account.investment_return.difference_amount
    : account.balance;
}

export default function Sectors({ accounts, onEdit, onAdd }: SectorsProps) {
  return (
    <section className="sectors">
      <div className="sectorsHeader">
        <h2>Accounts</h2>
        {/* No total here any more. Net worth, above, is the figure -- and it
            counts different things, so two totals on one page would sooner or
            later disagree in front of you. */}
        <div className="sectorsHeaderEnd">
          <button type="button" className="buttons addCourseButton" onClick={onAdd}>
            Add account
          </button>
        </div>
      </div>

      <div className="sectorGrid">
        {accounts.map((account) => (
          <div
            className={`sectorCard${account.kind === "debt" ? " sectorCard--debt" : ""}`}
            key={account.id}
          >
            {/* The stripe is decoration. The kind is also written out, because
                conveying it by colour alone leaves it unreadable to anyone who
                cannot tell these five apart -- the same reason the Jobs page
                spells out hourly, salaried and contract. */}
            <span className={`sectorKind sectorKind--${account.kind}`} aria-hidden="true" />

            {/* Opening the account is the card's job; editing is its own
                control, so one click never means two things. */}
            <Link className="sectorSelect" to={`/budget/accounts/${account.id}`}>
              <span className="sectorName">
                {account.name}
                <span className="sectorKindLabel">{KIND_LABELS[account.kind] ?? account.kind}</span>
              </span>
              <span className="sectorBalance">
                {formatMoney(worthOf(account))}
                {/* What the holding is worth over what went into it, on
                    investment accounts that have a reading. The balance alone
                    cannot say it: it is the sum of the ledger, so a holding that
                    doubled and one that halved read identically.

                    The sign is in the text and not only in the colour. Audit #60
                    is already open against this card for conveying an overdraft
                    by its minus sign alone, and a second meaning carried by
                    colour here would make that finding worse rather than better.

                    No HelpTip: this sits inside the card's Link, and the tip is a
                    button, so it would nest one interactive element in another.
                    The explanation lives on the account page. */}
                {account.investment_return?.return_percent != null && (
                  <>
                    <span className="sectorReturn" aria-hidden="true">
                      ({formatPercent(account.investment_return.return_percent, { signed: true })})
                    </span>
                    <span className="srOnly">
                      {returnInWords(
                        account.investment_return,
                        account.investment_return.return_percent,
                      )}
                    </span>
                  </>
                )}
              </span>
              {/* What went in, under what it is worth. Not decoration: the
                  percentage above divides by this figure, so printing it is what
                  lets a reader check the two against each other. Only on accounts
                  whose headline is no longer their ledger balance. */}
              {account.investment_return && (
                <span className="sectorPaidIn small-text muted">
                  {formatMoney(account.balance)} paid in
                </span>
              )}
              <span className="sectorShare small-text muted">
                {account.income_share > 0
                  ? `${account.income_share}% of income`
                  : "no income share"}
              </span>
            </Link>

            <button
              type="button"
              className="sectorEdit"
              onClick={() => onEdit(account)}
              aria-label={`Edit ${account.name}`}
              title="Edit account"
            >
              ✎
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
