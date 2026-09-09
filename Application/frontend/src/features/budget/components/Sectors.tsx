import { Account } from "../types";
import { formatMoney } from "../money";

interface SectorsProps {
  readonly accounts: readonly Account[];
  readonly selectedId: string | null;
  readonly onSelect: (accountId: string | null) => void;
}

/** The pots money sits in, with what each currently holds. */
export default function Sectors({ accounts, selectedId, onSelect }: SectorsProps) {
  const total = accounts.reduce((sum, account) => sum + account.balance, 0);

  return (
    <section className="sectors">
      <div className="sectorsHeader">
        <h2>Accounts</h2>
        <span className="sectorsTotal">{formatMoney(total)} total</span>
      </div>

      <div className="sectorGrid">
        {accounts.map((account) => {
          const active = selectedId === account.id;
          return (
            <button
              type="button"
              key={account.id}
              className={active ? "sectorCard sectorCardActive" : "sectorCard"}
              aria-pressed={active}
              onClick={() => onSelect(active ? null : account.id)}
            >
              <span className={`sectorKind sectorKind--${account.kind}`} />
              <span className="sectorName">{account.name}</span>
              <span className="sectorBalance">{formatMoney(account.balance)}</span>
              {account.income_share > 0 && (
                <span className="sectorShare small-text muted">
                  {account.income_share}% of income
                </span>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}
