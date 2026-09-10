import { Account } from "../types";
import { formatMoney } from "../money";

interface SectorsProps {
  readonly accounts: readonly Account[];
  readonly selectedId: string | null;
  readonly onSelect: (accountId: string | null) => void;
  readonly onEdit: (account: Account) => void;
}

/** The pots money sits in, with what each currently holds. */
export default function Sectors({ accounts, selectedId, onSelect, onEdit }: SectorsProps) {
  const total = accounts.reduce((sum, account) => sum + account.balance, 0);
  const shareTotal = accounts.reduce((sum, account) => sum + account.income_share, 0);

  return (
    <section className="sectors">
      <div className="sectorsHeader">
        <h2>Accounts</h2>
        <span className="sectorsTotal">
          {formatMoney(total)} total
          {shareTotal !== 100 && (
            <span className="small-text muted"> · shares {shareTotal.toFixed(0)}%</span>
          )}
        </span>
      </div>

      <div className="sectorGrid">
        {accounts.map((account) => {
          const active = selectedId === account.id;
          return (
            <div className={active ? "sectorCard sectorCardActive" : "sectorCard"} key={account.id}>
              <span className={`sectorKind sectorKind--${account.kind}`} />

              {/* Selecting filters the ledger; editing is its own control, so
                  one click never means two things. */}
              <button
                type="button"
                className="sectorSelect"
                aria-pressed={active}
                onClick={() => onSelect(active ? null : account.id)}
              >
                <span className="sectorName">{account.name}</span>
                <span className="sectorBalance">{formatMoney(account.balance)}</span>
                <span className="sectorShare small-text muted">
                  {account.income_share > 0
                    ? `${account.income_share}% of income`
                    : "no income share"}
                </span>
              </button>

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
          );
        })}
      </div>
    </section>
  );
}
