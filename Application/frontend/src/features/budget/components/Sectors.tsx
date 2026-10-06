import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Account, InvestmentReturn } from "../types";
import { formatMoney, formatPercent } from "../money";
import { monthLabel } from "../../../shared/utils/dateUtils";

interface SectorsProps {
  readonly accounts: readonly Account[];
  readonly onEdit: (account: Account) => void;
  readonly onAdd: () => void;
  /** Saves a new order, given every account id in it. No handles without it. */
  readonly onReorder?: (orderedIds: string[]) => Promise<void>;
}

/**
 * Which accounts need a new `position` for the cards to read in `orderedIds`.
 *
 * Only the ones whose stored position differs from their new index, so a move
 * of one card writes as few rows as it can. Every index is written out rather
 * than nudged: accounts created before ordering existed can share a position,
 * and only distinct ones make the order mean anything.
 */
export function positionChanges(
  accounts: readonly Account[],
  orderedIds: readonly string[],
): { id: string; position: number }[] {
  const stored = new Map(accounts.map((account) => [account.id, account.position]));
  return orderedIds
    .map((id, position) => ({ id, position }))
    .filter(({ id, position }) => stored.get(id) !== position);
}

function moved(ids: readonly string[], id: string, to: number) {
  const next = ids.filter((each) => each !== id);
  next.splice(Math.max(0, Math.min(to, next.length)), 0, id);
  return next;
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

export default function Sectors({ accounts, onEdit, onAdd, onReorder }: SectorsProps) {
  const gridRef = useRef<HTMLDivElement>(null);
  // The order on screen while a card is being moved or saved; null otherwise,
  // when the cards simply follow what the server last sent.
  const [order, setOrder] = useState<string[] | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const byId = new Map(accounts.map((account) => [account.id, account]));
  const shown = order
    ? order.map((id) => byId.get(id)).filter((account): account is Account => Boolean(account))
    : accounts;
  const canReorder = Boolean(onReorder) && accounts.length > 1;

  async function commit(ids: string[]) {
    setDragging(null);
    if (!onReorder || positionChanges(accounts, ids).length === 0) {
      setOrder(null);
      return;
    }
    setOrder(ids);
    setSaving(true);
    setError(null);
    try {
      await onReorder(ids);
    } catch {
      setError("Couldn't save the new order. Showing the order that was saved.");
    } finally {
      setSaving(false);
      setOrder(null);
    }
  }

  function startDrag(event: React.PointerEvent<HTMLButtonElement>, id: string) {
    if (saving) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setDragging(id);
    setOrder(accounts.map((account) => account.id));
  }

  // The card under the pointer, by its place in the grid. Works in a grid of any
  // shape, so the wrap at narrow widths needs no maths of its own.
  function dragOver(event: React.PointerEvent<HTMLButtonElement>) {
    if (!dragging || !order || !gridRef.current) return;
    const under = document.elementFromPoint?.(event.clientX, event.clientY);
    const card = under?.closest(".sectorCard");
    if (!card) return;
    const index = Array.from(gridRef.current.querySelectorAll(".sectorCard")).indexOf(card);
    if (index >= 0 && order[index] !== dragging) setOrder(moved(order, dragging, index));
  }

  function cancelDrag() {
    setDragging(null);
    setOrder(null);
  }

  // The same handle, by keyboard: one place per press, saved straight away.
  function nudge(event: React.KeyboardEvent<HTMLButtonElement>, id: string) {
    if (event.key === "Escape" && dragging) {
      cancelDrag();
      return;
    }
    const step = { ArrowUp: -1, ArrowLeft: -1, ArrowDown: 1, ArrowRight: 1 }[event.key];
    if (!step || saving || dragging) return;
    event.preventDefault();
    const ids = accounts.map((account) => account.id);
    // Past either end, moved() leaves the order as it was, and commit saves
    // nothing for an order that did not change.
    void commit(moved(ids, id, ids.indexOf(id) + step));
  }

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

      {saving && <p className="small-text muted" role="status">Saving order…</p>}
      {error && <p className="small-text error" role="alert">{error}</p>}

      <div className="sectorGrid" ref={gridRef}>
        {shown.map((account) => (
          <div
            className={[
              "sectorCard",
              account.kind === "debt" ? "sectorCard--debt" : "",
              dragging === account.id ? "sectorCard--dragging" : "",
            ].filter(Boolean).join(" ")}
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
                {/* Unticked in Settings: out of net worth and every figure
                    (D39). Said on the card, or the switch is invisible here. */}
                {account.counts_toward_net_worth === false && (
                  <span className="sectorKindLabel sectorUncounted">not counted</span>
                )}
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
              {/* Only when there is one. "no income share" stated the absence of
                  a setting, which is not information -- it filled a line on every
                  card that had nothing to say, and the eye learns to skip the
                  whole area. A card with no share simply does not mention shares. */}
              {account.income_share > 0 && (
                <span className="sectorShare small-text muted">
                  {account.income_share}% of income
                </span>
              )}
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

            {/* A sibling of the Link, like the pencil: a handle inside it would
                open the account on every drag. Pointer events rather than HTML
                drag-and-drop, which never fires on a touch screen. */}
            {canReorder && (
              <button
                type="button"
                className="sectorDrag"
                aria-label={`Reorder ${account.name}`}
                title="Drag to reorder, or use the arrow keys"
                disabled={saving}
                onPointerDown={(event) => startDrag(event, account.id)}
                onPointerMove={dragOver}
                onPointerUp={() => order && void commit(order)}
                onPointerCancel={cancelDrag}
                onKeyDown={(event) => nudge(event, account.id)}
              >
                ⠿
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
