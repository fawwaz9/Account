import { useEffect, useState } from "react";
import { fetchSalaries } from "./api";
import { SalaryFigure } from "./types";
import { formatMoney } from "../../budget/money";
import HelpTip from "../../../shared/components/HelpTip";

/**
 * "Co-op pay": each employer's typical hourly pay from offers students shared, verified and with
 * no names, above the floor; a one-line wait while there's none. Phase 3 item 12.
 */
export default function CoopPay({ userId }: { readonly userId: string }) {
  const [figures, setFigures] = useState<SalaryFigure[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSalaries(userId)
      .then((found) => { if (!cancelled) setFigures(found); })
      .catch(() => { if (!cancelled) setFigures(null); });
    return () => { cancelled = true; };
  }, [userId]);

  if (figures === null) return null;

  return (
    <section className="appSection coopPay" aria-label="Co-op pay">
      <div className="appSectionHead">
        <h2>Co-op pay</h2>
        <HelpTip label="About co-op pay">
          Offers students chose to share from their own applications, with no names. An offer counts once
          it matches the student&rsquo;s own job there, or 5 offers there agree, and figures change only in
          whole batches of 5, so no one offer can be picked out. Share yours from an offer&rsquo;s details.
        </HelpTip>
      </div>
      {figures.length === 0 ? (
        <p className="appSectionNote">
          Typical pay shows here once 5 students have shared verified offers from the same employer.
        </p>
      ) : (
        <ul className="coopPayList">
          {figures.map((figure) => (
            <li key={figure.employer}>
              <span className="coopPayEmployer">{figure.employer}</span>
              <span>
                {formatMoney(figure.median)}/h
                <span className="appSectionNote">
                  {" "}· middle half {formatMoney(figure.p25)}–{formatMoney(figure.p75)} · {figure.people} offers
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
