import { Link } from "react-router-dom";
import { Account } from "../types";
import { formatMoney } from "../money";

interface SectorsProps {
  readonly accounts: readonly Account[];
  readonly onEdit: (account: Account) => void;
}

/** The pots money sits in, with what each currently holds. */
const KIND_LABELS: Record<string, string> = {
  spending: "Spending",
  savings: "Savings",
  investment: "Investment",
  emergency: "Emergency",
  other: "Other",
};

export default function Sectors({ accounts, onEdit }: SectorsProps) {
  const total = accounts.reduce((sum, account) => sum + account.balance, 0);
  const shareTotal = accounts.reduce((sum, account) => sum + account.income_share, 0);

  return (
    <section className="sectors">
      <div className="sectorsHeader">
        <h2>Accounts</h2>
        <span className="sectorsTotal">
          Total: {formatMoney(total)}
        </span>
      </div>

      <div className="sectorGrid">
        {accounts.map((account) => (
          <div className="sectorCard" key={account.id}>
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
              <span className="sectorBalance">{formatMoney(account.balance)}</span>
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
